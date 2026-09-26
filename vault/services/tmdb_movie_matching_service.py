from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import Literal

from tmdbapis.exceptions import NotFound

from tmdb_adapter.client_singleton import get_tmdb_client
from vault.models import Movie


logger = logging.getLogger("vault.tmdb_sync")


MatchStatus = Literal["auto_match", "needs_confirmation", "needs_user_choice", "not_found"]
MediaType = Literal["movie", "tv"]


@dataclass(slots=True, frozen=True)
class TMDBCandidate:
    tmdb_id: int
    media_type: MediaType
    title: str
    original_title: str
    year: int | None
    score: int
    score_reasons: tuple[str, ...] = field(default_factory=tuple)
    poster_path: str | None = None
    popularity: float | None = None
    vote_average: float | None = None
    overview: str = ""


@dataclass(slots=True, frozen=True)
class TMDBMatchingResult:
    status: MatchStatus
    selected_candidate: TMDBCandidate | None
    candidates: tuple[TMDBCandidate, ...] = field(default_factory=tuple)
    message: str = ""


@dataclass(slots=True)
class _RawCandidate:
    tmdb_id: int
    media_type: MediaType
    title: str
    original_title: str
    year: int | None
    poster_path: str | None
    popularity: float | None
    vote_average: float | None
    overview: str = ""
    quick_score: int = 0
    alternative_titles: set[str] = field(default_factory=set)


@dataclass(slots=True, frozen=True)
class TitleVariants:
    raw: str
    primary_raw: str
    aliases_raw: tuple[str, ...]
    primary_norm: str
    aliases_norm: tuple[str, ...]
    full_norm: str

    @property
    def all_norms(self) -> tuple[str, ...]:
        result: list[str] = []
        for n in (self.primary_norm, *self.aliases_norm, self.full_norm):
            if n and n not in result:
                result.append(n)
        return tuple(result)


class TMDBMovieMatchingService:
    SCORE_ORIGINAL_EXACT = 60
    SCORE_LOCAL_EXACT = 50
    SCORE_ALTERNATIVE_TITLE = 35
    SCORE_YEAR_EXACT = 20
    SCORE_YEAR_NEAR = 10
    SCORE_MEDIA_TYPE_MATCH = 10

    AUTO_MATCH_MIN_SCORE = 90
    AMBIGUOUS_DELTA_THRESHOLD = 15
    MIN_RELEVANT_SCORE = 40
    SEARCH_RESULTS_PER_REQUEST = 8
    # Детали под альтернативные названия тянем только для топа по quick_score:
    # было 30 (минуты сети внутри синка одного фильма), стало 10.
    MAX_CANDIDATES_FOR_DETAIL = 10
    TOP_CANDIDATES_LIMIT = 5

    @classmethod
    def match_movie(cls, movie: Movie, top_n: int | None = None) -> TMDBMatchingResult:
        top_n = top_n or cls.TOP_CANDIDATES_LIMIT
        tmdb = get_tmdb_client()

        raw_candidates = cls._collect_candidates(tmdb, movie)
        if not raw_candidates:
            return cls._smart_search_fallback(
                movie,
                TMDBMatchingResult(
                    status="not_found",
                    selected_candidate=None,
                    candidates=tuple(),
                    message="Кандидаты TMDB не найдены",
                ),
            )

        expected_media_type = cls._expected_media_type(movie)
        movie_title_norm = cls.normalize_title(movie.title or "")
        original_title_norm = cls.normalize_title(movie.original_title or "")
        movie_title_variants = cls.extract_title_variants(movie.title or "")
        original_title_variants = cls.extract_title_variants(movie.original_title or "")

        cls._pre_score_candidates(
            raw_candidates=raw_candidates,
            movie=movie,
            movie_title_norm=movie_title_norm,
            original_title_norm=original_title_norm,
            expected_media_type=expected_media_type,
            movie_title_variants=movie_title_variants,
            original_title_variants=original_title_variants,
        )
        cls._enrich_with_alternative_titles(tmdb, raw_candidates)
        scored_candidates = cls._build_scored_candidates(
            raw_candidates=raw_candidates,
            movie=movie,
            movie_title_norm=movie_title_norm,
            original_title_norm=original_title_norm,
            expected_media_type=expected_media_type,
            movie_title_variants=movie_title_variants,
            original_title_variants=original_title_variants,
        )

        relevant = [candidate for candidate in scored_candidates if candidate.score >= cls.MIN_RELEVANT_SCORE]
        if not relevant:
            return cls._smart_search_fallback(
                movie,
                TMDBMatchingResult(
                    status="not_found",
                    selected_candidate=None,
                    candidates=tuple(scored_candidates[:top_n]),
                    message="Релевантные кандидаты TMDB не найдены",
                ),
            )

        best = relevant[0]
        second = relevant[1] if len(relevant) > 1 else None
        has_confident_winner = (
            best.score >= cls.AUTO_MATCH_MIN_SCORE
            and (second is None or (best.score - second.score) >= cls.AMBIGUOUS_DELTA_THRESHOLD)
        )

        if has_confident_winner:
            return TMDBMatchingResult(
                status="auto_match",
                selected_candidate=best,
                candidates=tuple(relevant[:top_n]),
                message="Найден уверенный матч TMDB",
            )

        # Singleton с точным названием + точным годом: в датасете Kinorium
        # original_title систематически грязный (английский международный тайтл
        # вместо оригинала, суффиксы изданий, пустое поле), поэтому недобор
        # до AUTO_MATCH_MIN_SCORE за счет original — не признак неуверенности.
        # Конкурентов нет, media-бонус не требуем (для ANIME expected=None
        # и бонус недостижим в принципе).
        if len(relevant) == 1 and cls._is_confident_singleton(best):
            return TMDBMatchingResult(
                status="auto_match",
                selected_candidate=best,
                candidates=(best,),
                message="Найден уверенный матч TMDB (единственный кандидат: точное название + год)",
            )

        if len(relevant) == 1:
            return cls._resolve_with_ai_if_confident(
                movie,
                TMDBMatchingResult(
                    status="needs_confirmation",
                    selected_candidate=None,
                    candidates=(best,),
                    message="Найден один неуверенный матч TMDB. Подтверди выбор вручную.",
                ),
            )

        return cls._resolve_with_ai_if_confident(
            movie,
            TMDBMatchingResult(
                status="needs_user_choice",
                selected_candidate=None,
                candidates=tuple(relevant[:top_n]),
                message="Найдено несколько релевантных кандидатов TMDB",
            ),
        )

    @classmethod
    def _resolve_with_ai_if_confident(cls, movie: Movie, result: TMDBMatchingResult) -> TMDBMatchingResult:
        """Тонкий делегат: весь fuzzy -> AI конвейер живет в TMDBMatchResolver."""
        from vault.services.tmdb_match_resolver import TMDBMatchResolver

        return TMDBMatchResolver.resolve_with_ai_if_confident(
            movie,
            result,
            auto_match_min_score=cls.AUTO_MATCH_MIN_SCORE,
        )

    @classmethod
    def _smart_search_fallback(cls, movie: Movie, fallback: TMDBMatchingResult) -> TMDBMatchingResult:
        """План Б: обычный конвейер ничего не нашёл — пробуем умный поиск.

        Ленивый импорт: smart-модуль зависит от этого сервиса сверху.
        Вердикт умного поиска (включая его not_found) замещает исходный,
        т.к. он проделал более глубокую попытку. При исключении — исходный fallback.
        TavilySearchError НЕ глотается: веб-поиск сломан — очередь должна
        остановиться с красным тостом, а не молча продолжать.
        """
        from vault.services.tavily_service import TavilySearchError
        from vault.services.tmdb_smart_search_service import smart_search

        try:
            return smart_search(movie)
        except TavilySearchError:
            raise
        except Exception as exc:
            logger.warning("SMART_SEARCH_FAILED | movie_id=%s | %s", getattr(movie, "id", None), exc)
            return fallback

    @classmethod
    def find_by_imdb_id(
        cls,
        imdb_id: str,
        *,
        expected_media_type: MediaType | None = None,
        top_n: int | None = None,
    ) -> TMDBMatchingResult:
        normalized_imdb_id = (imdb_id or "").strip()
        if not normalized_imdb_id:
            return TMDBMatchingResult(
                status="not_found",
                selected_candidate=None,
                candidates=tuple(),
                message="IMDb ID отсутствует",
            )

        top_n = top_n or cls.TOP_CANDIDATES_LIMIT
        tmdb = get_tmdb_client()

        try:
            result = tmdb.find_by_id(imdb_id=normalized_imdb_id)
        except Exception:
            return TMDBMatchingResult(
                status="not_found",
                selected_candidate=None,
                candidates=tuple(),
                message="TMDB lookup по IMDb ID завершился ошибкой",
            )

        candidates: list[TMDBCandidate] = []
        for media_type, attr_name in (("movie", "movie_results"), ("tv", "tv_results")):
            for item in getattr(result, attr_name, None) or []:
                candidate = cls._to_raw_candidate(item, media_type)
                if candidate is None:
                    continue
                candidates.append(
                    TMDBCandidate(
                        tmdb_id=candidate.tmdb_id,
                        media_type=media_type,
                        title=candidate.title,
                        original_title=candidate.original_title,
                        year=candidate.year,
                        score=cls.AUTO_MATCH_MIN_SCORE + (5 if media_type == expected_media_type else 0),
                        score_reasons=("imdb_id_lookup",),
                        poster_path=candidate.poster_path,
                        popularity=candidate.popularity,
                        vote_average=candidate.vote_average,
                    )
                )

        if not candidates:
            return TMDBMatchingResult(
                status="not_found",
                selected_candidate=None,
                candidates=tuple(),
                message="TMDB не вернул кандидатов по IMDb ID",
            )

        candidates.sort(
            key=lambda item: (
                item.media_type == expected_media_type,
                item.popularity or 0.0,
                item.vote_average or 0.0,
                item.year or 0,
            ),
            reverse=True,
        )

        filtered = [item for item in candidates if expected_media_type is None or item.media_type == expected_media_type]
        relevant = filtered or candidates
        best = relevant[0]
        if len(relevant) == 1:
            return TMDBMatchingResult(
                status="auto_match",
                selected_candidate=best,
                candidates=(best,),
                message="TMDB нашел уверенный матч по IMDb ID",
            )

        same_media = [item for item in relevant if item.media_type == best.media_type]
        if len(same_media) == 1 and expected_media_type is not None and best.media_type == expected_media_type:
            return TMDBMatchingResult(
                status="auto_match",
                selected_candidate=best,
                candidates=tuple(relevant[:top_n]),
                message="TMDB нашел уверенный матч по IMDb ID и типу медиа",
            )

        return TMDBMatchingResult(
            status="needs_user_choice",
            selected_candidate=None,
            candidates=tuple(relevant[:top_n]),
            message="TMDB вернул несколько кандидатов по IMDb ID",
        )

    @classmethod
    def normalize_title(cls, title: str) -> str:
        value = (title or "").lower().replace("ё", "е")
        value = cls._strip_edition_suffix(value)
        value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
        value = re.sub(r"_", " ", value)
        value = re.sub(r"\s+", " ", value)
        return value.strip()

    # Маркеры изданий/версий в trailing-скобках, которые не отличают фильмы:
    # "Captain America: Brave New World (IMAX)", "Носферату (Расширенная версия)".
    # Срез симметричен с обеих сторон (одинаковые скобки стираются везде,
    # разные издания одного фильма схлопываются), поэтому для матчинга безопасен.
    _TRAILING_PAREN_RE = re.compile(r"\s*[\(\[]([^()\[\]]*)[\)\]]\s*$")
    _EDITION_KEYWORD_RE = re.compile(
        r"\b(imax|extended|director|unrated|uncut|remaster|anniversary|theatrical|redux"
        r"|special edition|dolby|расширенная|расширенный|режиссерская|режиссерский"
        r"|полная версия|без цензуры|юбилейн|3d|4k)\b",
        re.IGNORECASE,
    )
    _PAREN_OR_BRACKET_RE = re.compile(r"[\(\[]([^()\[\]]+)[\)\]]")
    _MEDIA_FORMAT_KEYWORD_RE = re.compile(
        r"^(сериал|мини-сериал|телесериал|мультсериал|мультфильм|аниме|короткометражка|тв|фильм"
        r"|сезон\s*\d+|часть\s*\d+|season\s*\d+|part\s*\d+|series|tv series|movie|short|mini-series)$",
        re.IGNORECASE,
    )

    @classmethod
    def _strip_edition_suffix(cls, value: str) -> str:
        """Срезает trailing-скобки с маркерами изданий: (IMAX), (Extended Cut)..."""
        while True:
            match = cls._TRAILING_PAREN_RE.search(value)
            if not match:
                return value
            inner = match.group(1).strip()
            if not inner or not cls._EDITION_KEYWORD_RE.search(inner):
                return value
            value = value[: match.start()].rstrip()
            if not value:
                return value

    @classmethod
    def extract_title_variants(cls, raw: str) -> TitleVariants:
        """Раскладывает название на основное (primary) и альтернативные (aliases).

        Поддерживает:
        - Скобки: 'Голдфингер (Золотой палец)' -> primary 'Голдфингер', alias 'Золотой палец'
        - Слэши: 'Дюна / Dune' -> primary 'Дюна', alias 'Dune'
        - Игнорирует маркеры изданий (IMAX, Extended...) и типов медиа (сериал, фильм...).
        """
        cleaned = cls._clean_query(raw)
        if not cleaned:
            return TitleVariants(
                raw=raw or "",
                primary_raw="",
                aliases_raw=(),
                primary_norm="",
                aliases_norm=(),
                full_norm="",
            )

        full_norm = cls.normalize_title(cleaned)

        bracket_matches = [m.strip() for m in cls._PAREN_OR_BRACKET_RE.findall(cleaned) if m.strip()]
        outside = cls._PAREN_OR_BRACKET_RE.sub(" ", cleaned)
        outside = re.sub(r"\s+", " ", outside).strip()

        slash_parts = [p.strip() for p in outside.split("/") if p.strip()] if "/" in outside else [outside]
        if slash_parts and slash_parts[0]:
            primary_candidate = slash_parts[0]
            candidate_aliases = [*bracket_matches, *slash_parts[1:]]
        elif bracket_matches:
            primary_candidate = bracket_matches[0]
            candidate_aliases = bracket_matches[1:]
        else:
            primary_candidate = cleaned
            candidate_aliases = []

        primary_candidate = cls._strip_edition_suffix(primary_candidate).strip()
        primary_norm = cls.normalize_title(primary_candidate)

        valid_aliases_raw: list[str] = []
        valid_aliases_norm: list[str] = []

        for alias_item in candidate_aliases:
            alias_item_clean = cls._strip_edition_suffix(alias_item).strip()
            if not alias_item_clean:
                continue
            if cls._MEDIA_FORMAT_KEYWORD_RE.match(alias_item_clean):
                continue
            if cls._EDITION_KEYWORD_RE.search(alias_item_clean):
                continue
            if re.match(r"^(19\d{2}|20\d{2})$", alias_item_clean):
                continue
            alias_norm = cls.normalize_title(alias_item_clean)
            if alias_norm and alias_norm != primary_norm and alias_norm not in valid_aliases_norm:
                valid_aliases_raw.append(alias_item_clean)
                valid_aliases_norm.append(alias_norm)

        if not primary_norm and valid_aliases_norm:
            primary_candidate = valid_aliases_raw[0]
            primary_norm = valid_aliases_norm[0]
            valid_aliases_raw = valid_aliases_raw[1:]
            valid_aliases_norm = valid_aliases_norm[1:]

        return TitleVariants(
            raw=raw,
            primary_raw=primary_candidate,
            aliases_raw=tuple(valid_aliases_raw),
            primary_norm=primary_norm,
            aliases_norm=tuple(valid_aliases_norm),
            full_norm=full_norm,
        )

    @staticmethod
    def _is_confident_singleton(candidate: TMDBCandidate) -> bool:
        """Единственный кандидат с точным названием (RU или оригинал) + точным годом."""
        reasons = set(candidate.score_reasons or ())
        if "year_exact" not in reasons:
            return False
        return "title_exact" in reasons or "original_exact" in reasons

    @classmethod
    def _collect_candidates(cls, tmdb, movie: Movie) -> dict[tuple[str, int], _RawCandidate]:
        result: dict[tuple[str, int], _RawCandidate] = {}
        queries = cls._build_queries(movie)
        years = cls._build_year_window(movie.year)
        media_order = cls._media_search_order(movie)

        rounds = [(query, media_type, year) for query in queries for media_type in media_order for year in years]
        cls._run_search_rounds(tmdb, rounds, result)
        if not result and any(year is not None for year in years):
            # Год в базе может врать и вырезать всё фильтром: повтор без года.
            # Год при этом не пропадает — он отработает бонусами скоринга.
            fallback_rounds = [(query, media_type, None) for query in queries for media_type in media_order]
            cls._run_search_rounds(tmdb, fallback_rounds, result)
        return result

    @classmethod
    def _run_search_rounds(cls, tmdb, rounds: list, result: dict[tuple[str, int], _RawCandidate]) -> None:
        for query, media_type, year in rounds:
            items = cls._search_once(tmdb=tmdb, media_type=media_type, query=query, year=year)
            if not items:
                continue

            for item in items[: cls.SEARCH_RESULTS_PER_REQUEST]:
                raw = cls._to_raw_candidate(item, media_type)
                if raw is None:
                    continue
                key = (raw.media_type, raw.tmdb_id)
                existing = result.get(key)
                if existing is None or cls._is_better_raw(raw, existing):
                    result[key] = raw

    # Год, приклеенный к названию ("... 2023", "... (2023)"): TMDB ищет query
    # как литеральный текст, и год только убивает выдачу (обкатан в find_tmdb_id.py).
    _TRAILING_YEAR_PAREN_RE = re.compile(r"\s*\(\s*(19\d{2}|20\d{2})\s*\)\s*$")
    _TRAILING_YEAR_RE = re.compile(r"\s+(19\d{2}|20\d{2})\s*$")

    @classmethod
    def _clean_query(cls, value: str) -> str:
        """Срезает приклеенный к названию год и кавычки по краям."""
        text = (value or "").strip().strip("\"'«»").strip()
        text = cls._TRAILING_YEAR_PAREN_RE.sub("", text).strip()
        text = cls._TRAILING_YEAR_RE.sub("", text).strip()
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def _build_queries(cls, movie: Movie) -> list[str]:
        queries: list[str] = []
        seen: set[str] = set()
        for raw in (movie.original_title, movie.title):
            if not raw:
                continue
            cleaned = cls._clean_query(raw)
            if not cleaned:
                continue
            variants = cls.extract_title_variants(cleaned)
            candidate_texts = [variants.primary_raw, *variants.aliases_raw, cleaned]
            for text in candidate_texts:
                clean_item = cls._clean_query(text)
                if not clean_item:
                    continue
                norm = cls.normalize_title(clean_item)
                if not norm or norm in seen:
                    continue
                queries.append(clean_item)
                seen.add(norm)
        return queries

    @staticmethod
    def _build_year_window(year: int | None) -> list[int | None]:
        if not year:
            return [None]
        window = [year, year - 1, year + 1]
        return [y for y in window if y and y > 1800]

    @classmethod
    def _expected_media_type(cls, movie: Movie) -> MediaType | None:
        movie_type = movie.movie_type
        if movie_type in (Movie.MovieType.SERIES, Movie.MovieType.SHOW, Movie.MovieType.MINISERIES):
            return "tv"
        if movie_type in (Movie.MovieType.MOVIE, Movie.MovieType.CARTOON):
            return "movie"
        if movie_type == Movie.MovieType.ANIME:
            return None
        return "movie"

    @classmethod
    def _media_search_order(cls, movie: Movie) -> tuple[MediaType, ...]:
        expected = cls._expected_media_type(movie)
        if expected == "tv":
            return "tv", "movie"
        if expected == "movie":
            return "movie", "tv"
        return "movie", "tv"

    @classmethod
    def _search_once(cls, tmdb, media_type: MediaType, query: str, year: int | None):
        # limit: до 12 вызовов подряд на фильм — без лимитера ловим 429 от TMDB.
        from vault.services.tmdb_rate_limiter import TmdbRateLimiter

        TmdbRateLimiter.wait()
        try:
            if media_type == "movie":
                if year:
                    response = tmdb.movie_search(
                        query=query,
                        primary_release_year=year,
                        include_adult=True,
                    )
                else:
                    response = tmdb.movie_search(query=query, include_adult=True)
            else:
                if year:
                    response = tmdb.tv_search(
                        query=query,
                        first_air_date_year=year,
                        include_adult=True,
                    )
                else:
                    response = tmdb.tv_search(query=query, include_adult=True)
        except NotFound:
            return []
        except Exception:
            return []

        return response.results or []

    @classmethod
    def _to_raw_candidate(cls, item, media_type: MediaType) -> _RawCandidate | None:
        tmdb_id = cls._safe_int(getattr(item, "id", None))
        if not tmdb_id:
            return None

        title = cls._first_non_empty(getattr(item, "title", None), getattr(item, "name", None)) or ""
        original_title = cls._first_non_empty(
            getattr(item, "original_title", None),
            getattr(item, "original_name", None),
        ) or ""
        release_year = cls._extract_year(item)
        poster_path = getattr(item, "poster_path", None)
        popularity = cls._safe_float(getattr(item, "popularity", None))
        vote_average = cls._safe_float(getattr(item, "vote_average", None))
        overview = getattr(item, "overview", None) or ""

        return _RawCandidate(
            tmdb_id=tmdb_id,
            media_type=media_type,
            title=title,
            original_title=original_title,
            year=release_year,
            poster_path=poster_path,
            popularity=popularity,
            vote_average=vote_average,
            overview=overview,
        )

    @classmethod
    def _extract_year(cls, item) -> int | None:
        date_value = cls._first_non_empty(getattr(item, "release_date", None), getattr(item, "first_air_date", None))
        if date_value is None:
            return None
        return cls._safe_int(getattr(date_value, "year", None))

    @staticmethod
    def _first_non_empty(*values):
        for value in values:
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _safe_int(value) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_float(value) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_better_raw(left: _RawCandidate, right: _RawCandidate) -> bool:
        left_pop = left.popularity or 0.0
        right_pop = right.popularity or 0.0
        if left_pop != right_pop:
            return left_pop > right_pop
        left_vote = left.vote_average or 0.0
        right_vote = right.vote_average or 0.0
        return left_vote > right_vote

    @classmethod
    def _pre_score_candidates(
        cls,
        raw_candidates: dict[tuple[str, int], _RawCandidate],
        movie: Movie,
        movie_title_norm: str,
        original_title_norm: str,
        expected_media_type: MediaType | None,
        movie_title_variants: TitleVariants | None = None,
        original_title_variants: TitleVariants | None = None,
    ) -> None:
        if movie_title_variants is None:
            movie_title_variants = cls.extract_title_variants(movie.title or movie_title_norm or "")
        if original_title_variants is None:
            original_title_variants = cls.extract_title_variants(movie.original_title or original_title_norm or "")

        for raw in raw_candidates.values():
            score, _ = cls._score_candidate(
                raw=raw,
                movie=movie,
                movie_title_norm=movie_title_norm,
                original_title_norm=original_title_norm,
                expected_media_type=expected_media_type,
                include_alternative_titles=False,
                movie_title_variants=movie_title_variants,
                original_title_variants=original_title_variants,
            )
            raw.quick_score = score

    @classmethod
    def _enrich_with_alternative_titles(cls, tmdb, raw_candidates: dict[tuple[str, int], _RawCandidate]) -> None:
        limited = sorted(
            raw_candidates.values(),
            key=lambda c: (c.quick_score, c.popularity or 0.0, c.vote_average or 0.0),
            reverse=True,
        )[: cls.MAX_CANDIDATES_FOR_DETAIL]

        for raw in limited:
            try:
                from vault.services.tmdb_rate_limiter import TmdbRateLimiter

                TmdbRateLimiter.wait()
                details = tmdb.movie(raw.tmdb_id) if raw.media_type == "movie" else tmdb.tv_show(raw.tmdb_id)
            except Exception:
                continue

            detail_overview = getattr(details, "overview", None) or ""
            if len(detail_overview.strip()) > len((raw.overview or "").strip()):
                raw.overview = detail_overview

            alt_set: set[str] = set()
            for alternative in getattr(details, "alternative_titles", []) or []:
                value = cls._first_non_empty(getattr(alternative, "title", None), getattr(alternative, "name", None))
                normalized = cls.normalize_title(value or "")
                if normalized:
                    alt_set.add(normalized)
            raw.alternative_titles = alt_set

    @classmethod
    def _build_scored_candidates(
        cls,
        raw_candidates: dict[tuple[str, int], _RawCandidate],
        movie: Movie,
        movie_title_norm: str,
        original_title_norm: str,
        expected_media_type: MediaType | None,
        movie_title_variants: TitleVariants | None = None,
        original_title_variants: TitleVariants | None = None,
    ) -> list[TMDBCandidate]:
        if movie_title_variants is None:
            movie_title_variants = cls.extract_title_variants(movie.title or movie_title_norm or "")
        if original_title_variants is None:
            original_title_variants = cls.extract_title_variants(movie.original_title or original_title_norm or "")

        scored: list[TMDBCandidate] = []
        for raw in raw_candidates.values():
            score, reasons = cls._score_candidate(
                raw=raw,
                movie=movie,
                movie_title_norm=movie_title_norm,
                original_title_norm=original_title_norm,
                expected_media_type=expected_media_type,
                include_alternative_titles=True,
                movie_title_variants=movie_title_variants,
                original_title_variants=original_title_variants,
            )
            scored.append(
                TMDBCandidate(
                    tmdb_id=raw.tmdb_id,
                    media_type=raw.media_type,
                    title=raw.title,
                    original_title=raw.original_title,
                    year=raw.year,
                    score=score,
                    score_reasons=tuple(reasons),
                    poster_path=raw.poster_path,
                    popularity=raw.popularity,
                    vote_average=raw.vote_average,
                    overview=raw.overview,
                )
            )

        scored.sort(
            key=lambda candidate: (
                candidate.score,
                cls._year_priority(movie.year, candidate.year),
                candidate.popularity or 0.0,
                candidate.vote_average or 0.0,
            ),
            reverse=True,
        )
        return scored

    @classmethod
    def _score_candidate(
        cls,
        raw: _RawCandidate,
        movie: Movie,
        movie_title_norm: str,
        original_title_norm: str,
        expected_media_type: MediaType | None,
        include_alternative_titles: bool,
        movie_title_variants: TitleVariants | None = None,
        original_title_variants: TitleVariants | None = None,
    ) -> tuple[int, list[str]]:
        if movie_title_variants is None:
            movie_title_variants = cls.extract_title_variants(movie.title or movie_title_norm or "")
        if original_title_variants is None:
            original_title_variants = cls.extract_title_variants(movie.original_title or original_title_norm or "")

        score = 0
        reasons: list[str] = []

        candidate_title_norm = cls.normalize_title(raw.title)
        candidate_original_norm = cls.normalize_title(raw.original_title)

        if candidate_original_norm and (
            (original_title_variants.primary_norm and candidate_original_norm == original_title_variants.primary_norm)
            or (original_title_variants.full_norm and candidate_original_norm == original_title_variants.full_norm)
            or (candidate_original_norm in original_title_variants.aliases_norm)
        ):
            score += cls.SCORE_ORIGINAL_EXACT
            reasons.append("original_exact")
        elif (
            candidate_title_norm
            and candidate_title_norm in original_title_variants.all_norms
            and candidate_title_norm not in movie_title_variants.all_norms
        ):
            score += cls.SCORE_ORIGINAL_EXACT
            reasons.append("original_exact")

        if candidate_title_norm and (
            (movie_title_variants.primary_norm and candidate_title_norm == movie_title_variants.primary_norm)
            or (movie_title_variants.full_norm and candidate_title_norm == movie_title_variants.full_norm)
            or (candidate_title_norm in movie_title_variants.aliases_norm)
        ):
            score += cls.SCORE_LOCAL_EXACT
            reasons.append("title_exact")

        if include_alternative_titles:
            if "title_exact" not in reasons:
                if any(norm in raw.alternative_titles for norm in movie_title_variants.all_norms if norm):
                    score += cls.SCORE_ALTERNATIVE_TITLE
                    reasons.append("title_in_alternative")
            if "original_exact" not in reasons:
                if any(norm in raw.alternative_titles for norm in original_title_variants.all_norms if norm):
                    score += cls.SCORE_ALTERNATIVE_TITLE
                    reasons.append("original_in_alternative")

        if movie.year and raw.year:
            delta = abs(movie.year - raw.year)
            if delta == 0:
                score += cls.SCORE_YEAR_EXACT
                reasons.append("year_exact")
            elif delta == 1:
                score += cls.SCORE_YEAR_NEAR
                reasons.append("year_near")

        if expected_media_type and raw.media_type == expected_media_type:
            score += cls.SCORE_MEDIA_TYPE_MATCH
            reasons.append("media_type_match")

        return score, reasons

    @staticmethod
    def _year_priority(movie_year: int | None, candidate_year: int | None) -> float:
        if not movie_year or not candidate_year:
            return 0.0
        delta = abs(movie_year - candidate_year)
        if delta == 0:
            return 1.0
        if delta == 1:
            return 0.5
        return 0.0
