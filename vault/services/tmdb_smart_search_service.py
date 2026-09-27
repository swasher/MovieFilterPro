from __future__ import annotations

import logging
from dataclasses import dataclass

from moviefilter.models import UserPreferences
from tmdb_adapter.client_singleton import get_tmdb_client, get_tmdb_client_en
from vault.models import Movie
from vault.services.tmdb_ai_matching_service import TMDBAIMatchingService
from vault.services.tmdb_match_resolver import TMDBMatchResolver
from vault.services.tmdb_movie_matching_service import (
    TMDBCandidate,
    TMDBMatchingResult,
    TMDBMovieMatchingService,
)
from vault.services.web_search_service import WebSearchError, WebSearchService
from web_logger import send_match_log


logger = logging.getLogger("vault.tmdb_sync")


# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #

# Пороги уверенности сюжета: базовый берут score 4 и 5 локального AI,
# строгий (год расходится) — только score 5 («сюжет ТОЧНО ТОТ»).
SMART_BASE_THRESHOLD = 0.6
SMART_STRICT_THRESHOLD = 0.9
SMART_MAX_VALIDATIONS = 10
SMART_MIN_PLOT_CHARS = 40

SMART_REASON_PLOT_MATCH = "smart_search_plot_match"

MSG_NO_QUERIES = "Умный поиск: нет названий для запроса"
MSG_SHORT_PLOT = "Умный поиск: описание слишком короткое для сверки"
MSG_NO_CANDIDATES = "Умный поиск: кандидаты TMDB не найдены"
MSG_AI_UNAVAILABLE = "Умный поиск TMDB: локальный AI недоступен"
MSG_NO_PLOT_MATCH = "Умный поиск: совпадение по сюжетам не найдено"
MSG_PLOT_MATCH = "Умный поиск TMDB: найдено совпадение по сюжету"


@dataclass(slots=True)
class SmartCandidate:
    """Слитый кандидат умного поиска: названия и описания с ru+en выдач."""

    tmdb_id: int
    media_type: str = "movie"
    title: str = ""
    original_title: str = ""
    year: int | None = None
    alt_titles: tuple[str, ...] = ()
    overview_ru: str = ""
    overview_en: str = ""


def coerce_year(value: object) -> int | None:
    """Безопасный парсинг года: мусор и пусто -> None."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return None


def release_year(release_date: object) -> int | None:
    """Год из 'YYYY-MM-DD' TMDB."""
    if not release_date:
        return None
    return coerce_year(str(release_date)[:4])


def title_variants(candidate: SmartCandidate) -> list[str]:
    """Все известные названия кандидата без дублей и пустых."""
    variants: list[str] = []
    for raw in (candidate.title, candidate.original_title, *candidate.alt_titles):
        text = (raw or "").strip()
        if text and text not in variants:
            variants.append(text)
    return variants


def rank_candidates(
    candidates: list[SmartCandidate],
    clean_title: str,
    llm_year: int | None,
) -> list[tuple[SmartCandidate, int, int]]:
    """Сортирует кандидатов по дешёвым бонусам: название +3/+1, год +2/+1.

    Возвращает (кандидат, title_bonus, year_bonus) по убыванию суммы бонусов,
    при равенстве — исходный порядок (сортировка стабильная).
    """
    norm_clean = TMDBMovieMatchingService.normalize_title(clean_title or "")
    scored: list[tuple[int, int, SmartCandidate, int, int]] = []
    for order, candidate in enumerate(candidates):
        norms = []
        for variant in title_variants(candidate):
            norm = TMDBMovieMatchingService.normalize_title(variant)
            if norm and norm not in norms:
                norms.append(norm)
        title_bonus = 0
        if norm_clean and norm_clean in norms:
            title_bonus = 3
        elif norm_clean and any(norm_clean in norm or norm in norm_clean for norm in norms):
            title_bonus = 1
        year_bonus = 0
        if llm_year is not None and candidate.year is not None:
            gap = abs(candidate.year - llm_year)
            year_bonus = 2 if gap == 0 else (1 if gap == 1 else 0)
        scored.append((-(title_bonus + year_bonus), order, candidate, title_bonus, year_bonus))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [(candidate, title_bonus, year_bonus) for _, _, candidate, title_bonus, year_bonus in scored]


def plots_match_literally(plot1: str, plot2: str) -> bool:
    """Только дословное равенство нормализованных текстов.

    Вхождение одного текста в другой НЕ засчитывается: короткий синопсис
    может целиком входить в длинное описание совершенно другого фильма.
    """
    left = TMDBMatchResolver._normalize_plot(plot1)
    right = TMDBMatchResolver._normalize_plot(plot2)
    if len(left) < TMDBMatchResolver.LITERAL_MIN_CHARS or len(right) < TMDBMatchResolver.LITERAL_MIN_CHARS:
        return False
    return left == right


def _item_year(item: object) -> int | None:
    date_value = getattr(item, "release_date", None) or getattr(item, "first_air_date", None)
    if date_value is None:
        return None
    year = getattr(date_value, "year", None)
    if year is not None:
        return coerce_year(year)
    return coerce_year(str(date_value)[:4])


def _merge_item(
    merged: dict[tuple[str, int], SmartCandidate],
    item: object,
    media_type: str,
    lang_key: str,
) -> None:
    tmdb_id = TMDBMovieMatchingService._safe_int(getattr(item, "id", None))
    if not tmdb_id:
        return
    first_non_empty = TMDBMovieMatchingService._first_non_empty
    title = first_non_empty(getattr(item, "title", None), getattr(item, "name", None)) or ""
    original = first_non_empty(getattr(item, "original_title", None), getattr(item, "original_name", None)) or ""
    overview = getattr(item, "overview", None) or ""
    year = _item_year(item)

    key = (media_type, tmdb_id)
    record = merged.get(key)
    if record is None:
        merged[key] = SmartCandidate(
            tmdb_id=tmdb_id,
            media_type=media_type,
            title=title,
            original_title=original,
            year=year,
            overview_ru=overview if lang_key == "ru" else "",
            overview_en=overview if lang_key == "en" else "",
        )
        return
    for variant in (title, original):
        if variant and variant != record.title and variant != record.original_title and variant not in record.alt_titles:
            record.alt_titles = (*record.alt_titles, variant)
    if overview:
        if lang_key == "ru" and not record.overview_ru:
            record.overview_ru = overview
        elif lang_key == "en" and not record.overview_en:
            record.overview_en = overview
    if record.year is None and year is not None:
        record.year = year


def collect_candidates(
    *,
    tmdb_ru,
    tmdb_en,
    queries: list[str],
    media_order: tuple[str, ...] = ("movie", "tv"),
) -> list[SmartCandidate]:
    """Year-free поиск по запросам на ru+en, слияние по (media_type, tmdb_id).

    Год сознательно не передаём в поиск (урок find_tmdb_id.py): он работает
    только как бонус ранжирования. Лимитер 429 уже внутри _search_once.
    Первыми видны ru-названия/описания, en-варианты копятся в alt_titles.
    """
    merged: dict[tuple[str, int], SmartCandidate] = {}
    for query in queries:
        if not (query or "").strip():
            continue
        for lang_key, client in (("ru", tmdb_ru), ("en", tmdb_en)):
            for media_type in media_order:
                items = TMDBMovieMatchingService._search_once(
                    tmdb=client, media_type=media_type, query=query, year=None
                )
                for item in items or []:
                    _merge_item(merged, item, media_type, lang_key)
    return list(merged.values())


def is_local_ai_available() -> bool:
    """Локальный AI настроен (флаг + base_url + модель). Только он используется в умном поиске."""
    try:
        prefs = UserPreferences.get()
    except Exception:
        return False
    if prefs is None or not getattr(prefs, "ai_enabled", False):
        return False
    base_url = (getattr(prefs, "ai_base_url", "") or "").strip()
    model = (getattr(prefs, "ai_model", "") or "").strip()
    return bool(base_url and model)


def _effective_threshold(movie_year: int | None, candidate_year: int | None) -> float:
    if movie_year is not None and candidate_year is not None and abs(movie_year - candidate_year) > 1:
        return SMART_STRICT_THRESHOLD
    return SMART_BASE_THRESHOLD


def score_candidates(
    movie: Movie,
    ranked: list[tuple[SmartCandidate, int, int]],
    *,
    allow_ai: bool,
) -> list[dict]:
    """Скоринг топа: дословное равенство — 1.0 без LLM, остальное — локальный AI.

    Возвращает записи {candidate, score, eff, tb, yb, order, reason}.
    Кандидаты, которых сравнить не удалось, пропускаются (ошибка ≠ «разные»).
    """
    source_plot = movie.description or ""
    scored: list[dict] = []
    for order, (candidate, title_bonus, year_bonus) in enumerate(ranked[:SMART_MAX_VALIDATIONS]):
        ru = (candidate.overview_ru or "").strip()
        en = (candidate.overview_en or "").strip()
        overview = ru or en
        if not overview:
            logger.info("SMART_SEARCH_SKIP | tmdb_id=%s | reason=overview_empty", candidate.tmdb_id)
            continue
        eff = _effective_threshold(movie.year, candidate.year)
        if (ru and plots_match_literally(source_plot, ru)) or (en and plots_match_literally(source_plot, en)):
            logger.info("SMART_SEARCH_LITERAL | tmdb_id=%s", candidate.tmdb_id)
            scored.append({
                "candidate": candidate, "score": 1.0, "eff": eff,
                "tb": title_bonus, "yb": year_bonus, "order": order,
                "reason": "plot_literal_match",
            })
            continue
        if not allow_ai:
            continue
        # Если есть оба описания и они не идентичны, передаем оба для полноты контекста
        if ru and en and ru != en:
            overview_for_ai = f"{ru}\n\n[English overview]:\n{en}"
        else:
            overview_for_ai = overview

        # ВАЖНО: confidence у локального AI — это уверенность в вердикте,
        # а не похожесть сюжетов. same_work=False + confidence=1.0 означает
        # «точно РАЗНЫЕ фильмы». Проверяем вердикт, а не число.
        comparison = TMDBAIMatchingService.compare_plots(
            source_plot,
            overview_for_ai,
            title=movie.title or candidate.title or "",
            original_title=movie.original_title or candidate.original_title or "",
            year=movie.year or candidate.year,
        )
        if comparison is None:
            logger.info("SMART_SEARCH_SKIP | tmdb_id=%s | reason=ai_unavailable", candidate.tmdb_id)
            continue
        send_match_log(
            "ai_score",
            tmdb_id=candidate.tmdb_id,
            same_work=comparison.same_work,
            confidence=round(comparison.confidence, 2),
        )
        if not comparison.same_work or comparison.red_flags:
            logger.info(
                "SMART_SEARCH_REJECTED | tmdb_id=%s | same_work=%s | red_flags=%s",
                candidate.tmdb_id, comparison.same_work, ";".join(comparison.red_flags),
            )
            continue
        scored.append({
            "candidate": candidate, "score": comparison.confidence, "eff": eff,
            "tb": title_bonus, "yb": year_bonus, "order": order,
            "reason": SMART_REASON_PLOT_MATCH,
        })
    return scored


def pick_winner(scored: list[dict]) -> dict | None:
    """Аргмакс по скорам; ничья на первом месте — тай-брейк по бонусам ранга."""
    contenders = [s for s in scored if s["score"] >= s["eff"]]
    if not contenders:
        return None
    ordered = sorted(contenders, key=lambda s: -s["score"])
    if len(ordered) == 1 or ordered[0]["score"] > ordered[1]["score"]:
        return ordered[0]
    tied = [c for c in ordered if c["score"] == ordered[0]["score"]]
    tied.sort(key=lambda c: (-(c["tb"] + c["yb"]), c["order"]))
    return tied[0]


def _to_tmdb_candidate(entry: dict) -> TMDBCandidate:
    candidate = entry["candidate"]
    return TMDBCandidate(
        tmdb_id=candidate.tmdb_id,
        media_type=candidate.media_type,
        title=candidate.title,
        original_title=candidate.original_title,
        year=candidate.year,
        score=int(round(entry["score"] * 100)),
        score_reasons=(entry["reason"],),
        overview=candidate.overview_ru or candidate.overview_en,
    )


def _not_found(message: str) -> TMDBMatchingResult:
    return TMDBMatchingResult(
        status="not_found",
        selected_candidate=None,
        candidates=tuple(),
        message=message,
    )


def enrich_queries_from_web(movie: Movie, queries: list[str]) -> tuple[list[str], str, int | None]:
    """Шаги 1-2 (урок find_tmdb_id.py): веб-поиск + извлечение подсказок локальным AI.

    Веб-поиск идёт через WebSearchService: SearXNG, если задан его URL, иначе Tavily.
    Возвращает (queries, clean_title, llm_year). WebSearchError намеренно
    пробрасывается наверх: если веб-поиск не работает, очередь TMDB sync должна
    остановиться с красным тостом, а не молча продолжать.
    """
    provider = WebSearchService.get_provider()
    try:
        web_context = WebSearchService.search_web(
            movie.title or "",
            movie.original_title or "",
            movie.description or "",
        )
    except WebSearchError:
        send_match_log("web_search", engine=provider or "none", ok=False)
        raise
    send_match_log("web_search", engine=provider or "none", ok=True)

    clean_title = movie.original_title or movie.title or ""
    llm_year = movie.year
    if not (web_context or "").strip():
        return queries, clean_title, llm_year

    hints = TMDBAIMatchingService.extract_web_hints(
        title=movie.title or "",
        original_title=movie.original_title or "",
        plot=movie.description or "",
        web_context=web_context,
    )
    if hints:
        queries_before = len(queries)
        for raw_query in hints.get("tmdb_queries") or []:
            cleaned = TMDBMovieMatchingService._clean_query(raw_query)
            if cleaned and cleaned not in queries:
                queries.append(cleaned)
        if (hints.get("clean_title") or "").strip():
            clean_title = hints["clean_title"].strip()
        if hints.get("year") is not None:
            llm_year = hints["year"]
        send_match_log(
            "ai_web_hints",
            clean_title=clean_title,
            llm_year=llm_year,
            queries_added=len(queries) - queries_before,
        )
    return queries, clean_title, llm_year


def smart_search(movie: Movie) -> TMDBMatchingResult:
    """Fallback матчинга: веб-подсказки (SearXNG/Tavily), year-free поиск ru+en, ранг, проверка сюжетов локальным AI.

    Groq здесь не используется по решению владельца — только локальный AI.
    Без локального AI возможен лишь дословный матч, иначе not_found.
    Без описания (короче SMART_MIN_PLOT_CHARS) сверять нечего — поиск не запускаем.
    Веб-поиск обязателен: сбой (WebSearchError) останавливает очередь.
    """
    send_match_log(
        "smart_search_start",
        movie_id=getattr(movie, "id", None),
        title=movie.title or "",
    )
    if len((movie.description or "").strip()) < SMART_MIN_PLOT_CHARS:
        return _not_found(MSG_SHORT_PLOT)
    queries = TMDBMovieMatchingService._build_queries(movie)
    if not queries:
        return _not_found(MSG_NO_QUERIES)

    queries, clean_title, llm_year = enrich_queries_from_web(movie, queries)

    media_order = TMDBMovieMatchingService._media_search_order(movie)
    collected = collect_candidates(
        tmdb_ru=get_tmdb_client(),
        tmdb_en=get_tmdb_client_en(),
        queries=queries,
        media_order=media_order,
    )
    if not collected:
        return _not_found(MSG_NO_CANDIDATES)

    ranked = rank_candidates(collected, clean_title, llm_year)
    allow_ai = is_local_ai_available()
    scored = score_candidates(movie, ranked, allow_ai=allow_ai)
    winner = pick_winner(scored)
    if winner is None:
        if not allow_ai:
            logger.info("SMART_SEARCH_NO_AI | movie_id=%s", getattr(movie, "id", None))
            return _not_found(MSG_AI_UNAVAILABLE)
        if ranked:
            best = ranked[0][0]
            logger.info(
                "SMART_SEARCH_UNVALIDATED | tmdb_id=%s | title=%s | year=%s",
                best.tmdb_id, best.title, best.year,
            )
        return _not_found(MSG_NO_PLOT_MATCH)

    selected = _to_tmdb_candidate(winner)
    logger.info(
        "SMART_SEARCH_MATCH | movie_id=%s | tmdb_id=%s | score=%.2f",
        getattr(movie, "id", None), selected.tmdb_id, winner["score"],
    )
    return TMDBMatchingResult(
        status="auto_match",
        selected_candidate=selected,
        candidates=(selected,),
        message=MSG_PLOT_MATCH,
    )


# ------------------------------------ #
#            DOMAIN LAYER              #
# ------------------------------------ #
# Доменной логики пока нет: сравнение сюжетов через локальный AI
# (TMDBAIMatchingService.compare_plots) и оркестрация появятся
# следующими шагами поверх этих хелперов.
