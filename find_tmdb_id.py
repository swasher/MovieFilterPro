import glob
import html
import json
import os
import re
import sys
from dataclasses import dataclass

import requests
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")


@dataclass(slots=True, frozen=True)
class LLMProvider:
    name: str
    base_url: str
    model: str
    api_key: str = ""
    needs_auth: bool = True
    use_response_format: bool = True


OPENROUTER = LLMProvider(
    name="openrouter",
    base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip().rstrip("/"),
    model=os.getenv("OPENROUTER_MODEL", "stealth/space-bunny-alpha").strip(),
    # model=os.getenv("OPENROUTER_MODEL", "qwen/qwen3.8-27b:free").strip(),
    api_key=(os.getenv("OPENROUTER_API_KEY") or "").strip(),
    needs_auth=True,
    use_response_format=True,
)

LOCAL = LLMProvider(
    name="local",
    base_url="http://localhost:8888/v1",
    model="unsloth/Qwen3.5-9B-GGUF:UD-Q4_K_XL",
    api_key=os.getenv("LOCAL_LLM_API_KEY", "").strip(),
    needs_auth=False,
    use_response_format=False,
)

# Переключение одной строкой: ACTIVE_PROVIDER = LOCAL
ACTIVE_PROVIDER = LOCAL

LLM_REQUEST_TIMEOUT_SECONDS = 15

PLOT_MIN_PLOT_CHARS = 40
PLOT_REQUEST_TIMEOUT_SECONDS = 30
PLOT_STRICT_THRESHOLD = 0.75
PLOT_WIN_MARGIN = 0.10
MAX_PLOT_VALIDATIONS = 10
# Дискретная шкала LLM -> confidence: 4 проходит оба порога, 3 не проходит ни один.
PLOT_SCORE_MAP = {5: 1.0, 4: 0.8, 3: 0.45, 2: 0.2, 1: 0.0}

PLOT_SYSTEM_PROMPT = """
Ты — система анализа сходства текстов.
Твоя задача — сравнить два описания сюжетов фильмов и определить, описывают ли они один и тот же фильм.

Правила анализа:
1. Имена собственные и уникальные детали:
   - Совпадение редких имен персонажей, специфических топонимов (названий городов, заведений), нестандартных предметов или уникальных комбинаций имен — сильный признак одного фильма, даже если одно из описаний гораздо короче другого.
   - Частые имена или общеизвестные локации сами по себе совпадения не доказывают, смотри на сюжетный контекст.

2. Сюжетный контекст:
   - Сравнивай ключевые действия, роли персонажей и завязку конфликта.
   - Одно описание может быть краткой аннотацией, а второе — подробным пересказом. Игнорируй разницу в объеме, стиле и детализации, если ключевые факты совпадают.

Оцени пару целой оценкой от 1 до 5:
- 5 — точно один фильм: совпадают уникальные имена/топонимы и ключевые события.
- 4 — тот же сюжет, но детали расходятся или их не хватает для полной уверенности.
- 3 — похожая завязка или жанр, но это вполне могут быть разные фильмы.
- 2 — описания противоречат друг другу в ключевых фактах.
- 1 — совершенно разные события и персонажи.

Верни ответ строго в формате JSON:
- 'score': целое число от 1 до 5.
- 'reason': краткое объяснение, какие именно элементы (имена, локации, события) повлияли на оценку.
"""

tavily_client = TavilyClient(api_key=TAVILY_API_KEY)


def _clip_plot(value: str, max_chars: int = 1800) -> str:
    text = (value or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}..."


LITERAL_MIN_CHARS = 50


def _normalize_plot(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"_", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _plots_match_literally(plot1: str, plot2: str) -> bool:
    """Только дословное равенство нормализованных текстов (сайты копируют описания друг у друга)."""
    left = _normalize_plot(plot1)
    right = _normalize_plot(plot2)
    if len(left) < LITERAL_MIN_CHARS or len(right) < LITERAL_MIN_CHARS:
        return False
    return left == right


def _clamp_confidence(value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, result))


def _map_plot_score(value: object) -> float:
    """Дискретная оценка 1-5 -> confidence. Мусор -> 0.0."""
    try:
        level = int(round(float(value)))
    except (TypeError, ValueError):
        return 0.0
    level = max(1, min(5, level))
    return PLOT_SCORE_MAP[level]


def _parse_json_object(content: str) -> dict | None:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except ValueError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except ValueError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_llm_data(parsed: object, original_title: str, title: str) -> dict:
    """Достаёт clean_title/year/tmdb_queries, даже если LLM обернула их во вложенный объект."""
    fallback = {"clean_title": original_title, "year": None, "tmdb_queries": [original_title, title]}
    if not isinstance(parsed, dict):
        return fallback
    data = parsed
    if "clean_title" not in data and "tmdb_queries" not in data:
        for value in data.values():
            if isinstance(value, dict) and ("clean_title" in value or "tmdb_queries" in value):
                data = value
                break
    queries = data.get("tmdb_queries") or []
    if isinstance(queries, str):
        queries = [queries]
    queries = [str(q).strip() for q in queries if isinstance(q, (str, int, float)) and str(q).strip()]
    return {
        "clean_title": str(data.get("clean_title") or original_title).strip() or original_title,
        "year": _coerce_year(data.get("year")),
        "tmdb_queries": queries or [original_title, title],
    }


def _chat_completions_url(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _normalize_title(value: object) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _clean_tmdb_query(query: object) -> str:
    """Убирает мусор, который LLM иногда клеит к названию: год, кавычки."""
    text = str(query or "").strip().strip("\"'«»").strip()
    text = re.sub(r"\s*\(\s*(19\d{2}|20\d{2})\s*\)\s*$", "", text).strip()
    text = re.sub(r"\s+(19\d{2}|20\d{2})\s*$", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    if re.fullmatch(r"19\d{2}|20\d{2}", text):
        return ""  # один год без названия — искать бессмысленно
    return text


def _coerce_year(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _release_year(release_date: object) -> int | None:
    if not release_date:
        return None
    return _coerce_year(str(release_date)[:4])


def _rank_candidates(candidates: list, clean_title: str, llm_year: int | None) -> list:
    """Сортирует (movie, qi, pos) по дешёвым бонусам: название +3/+1, год +2/+1."""
    norm_clean = _normalize_title(clean_title)
    scored = []
    for order, (movie, qi, pos) in enumerate(candidates):
        norms = []
        for variant in [movie.get("title", ""), movie.get("original_title", "")] + list(movie.get("_alt_titles") or []):
            norm = _normalize_title(variant)
            if norm and norm not in norms:
                norms.append(norm)
        title_bonus = 0
        if norm_clean and norm_clean in norms:
            title_bonus = 3
        elif norm_clean and any(norm_clean in n or n in norm_clean for n in norms):
            title_bonus = 1
        cand_year = _release_year(movie.get("release_date"))
        if llm_year is not None and cand_year is not None:
            gap = abs(cand_year - llm_year)
            year_bonus = 2 if gap == 0 else (1 if gap == 1 else 0)
        else:
            year_bonus = 0
        scored.append((-(title_bonus + year_bonus), qi, pos, order, movie, title_bonus, year_bonus))
    scored.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    return [(movie, title_bonus, year_bonus) for _, _, _, _, movie, title_bonus, year_bonus in scored]


def compare_plots(target_plot: str, candidate_plot: str, provider: LLMProvider | None = None) -> float:
    """
    Сравнение сюжетов через ACTIVE_PROVIDER (как TMDBGROQMatchingService.compare_pair).
    provider: None (= ACTIVE_PROVIDER), либо OPENROUTER / LOCAL.
    Возвращает confidence 0.0..1.0. 0.0 — разные фильмы / ошибка / короткие описания.
    """
    cfg = provider or ACTIVE_PROVIDER
    label = cfg.name
    if len((target_plot or "").strip()) < PLOT_MIN_PLOT_CHARS:
        return 0.0
    if len((candidate_plot or "").strip()) < PLOT_MIN_PLOT_CHARS:
        return 0.0
    if _plots_match_literally(target_plot, candidate_plot):
        print(f"  [{label}] дословное совпадение сюжетов — LLM не вызываю")
        return 1.0
    if not cfg.model:
        print(f"Ошибка сравнения сюжетов [{label}]: не задана модель.")
        return 0.0
    if cfg.needs_auth and not cfg.api_key:
        print(f"Ошибка сравнения сюжетов [{label}]: не задан API-ключ.")
        return 0.0

    user_prompt = (
        f"Описание 1:\n{_clip_plot(target_plot)}\n\n"
        f"Описание 2:\n{_clip_plot(candidate_plot)}"
    )

    url = _chat_completions_url(cfg.base_url)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    payload: dict = {
        "model": cfg.model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": PLOT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    if cfg.use_response_format:
        payload["response_format"] = {"type": "json_object"}

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=PLOT_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as e:
        print(f"Ошибка сравнения сюжетов [{label}]: {e}")
        return 0.0

    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not choices:
        print(f"Ошибка сравнения сюжетов [{label}]: пустой choices в ответе")
        return 0.0
    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = message.get("content", "")
    if not isinstance(content, str) or not content.strip():
        print(f"Ошибка сравнения сюжетов [{label}]: пустой content в ответе")
        return 0.0

    parsed = _parse_json_object(content)
    if parsed is None:
        print(f"Ошибка сравнения сюжетов [{label}]: не JSON в ответе: {content[:500]}")
        return 0.0

    if "score" in parsed:
        confidence = _map_plot_score(parsed.get("score"))
        raw_mark = f"score={parsed.get('score')}"
    else:  # fallback на старый формат с непрерывным confidence
        confidence = _clamp_confidence(parsed.get("confidence"))
        raw_mark = f"confidence={parsed.get('confidence')}"
    reason = str(parsed.get("reason", "") or "").strip()[:500]
    if reason:
        print(f"  [{label}] {raw_mark} -> confidence={confidence:.2f} reason={reason}")
    else:
        print(f"  [{label}] {raw_mark} -> confidence={confidence:.2f}")
    return confidence


def step1_search_web(title: str, original_title: str) -> str:
    """
    ШАГ 1: Поиск в интернете по исходным данным.
    """
    query = f"{title} {original_title} movie film"
    try:
        response = tavily_client.search(query=query, search_depth="basic", max_results=5)

        web_context = ""
        for r in response.get("results", []):
            web_context += f"Заголовок: {r.get('title')}\nКонтент: {r.get('content')}\n\n"
        return web_context
    except Exception as e:
        print(f"Ошибка веб-поиска: {e}")
        return ""


def step2_extract_data_with_llm(title: str, original_title: str, plot: str, web_context: str, provider: LLMProvider | None = None) -> dict:
    """
    ШАГ 2: LLM анализирует результаты веба и извлекает чистые данные.
    provider: None (= ACTIVE_PROVIDER), либо OPENROUTER / LOCAL.
    """
    prompt = f"""
    Тебе даны искаженные данные фильма и результаты поиска в интернете по этим данным.

    Исходные данные:
    Title: {title}
    Original Title: {original_title}
    Plot: {plot}

    Результаты веб-поиска:
    {web_context}

    Задача: На основе веб-поиска определи точное официальное оригинальное название фильма и год выхода.
    Сформируй 2-3 точных запроса для базы данных TMDb (только названия, без года и лишних слов).

    Верни ответ СТРОГО в формате JSON:
    {{
      "clean_title": "Точное оригинальное/международное название",
      "year": 2024,
      "tmdb_queries": ["Запрос 1", "Запрос 2"]
    }}
    """

    cfg = provider or ACTIVE_PROVIDER
    label, url, model, api_key = cfg.name, _chat_completions_url(cfg.base_url), cfg.model, cfg.api_key
    if not model:
        print(f"Ошибка LLM [{label}]: не задана модель.")
        return {"clean_title": original_title, "year": None, "tmdb_queries": [original_title, title]}
    if cfg.needs_auth and not api_key:
        print(f"Ошибка LLM [{label}]: не задан API-ключ. Запрос не отправлен.")
        return {"clean_title": original_title, "year": None, "tmdb_queries": [original_title, title]}

    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
    }
    if cfg.use_response_format:
        payload["response_format"] = {"type": "json_object"}

    print(f"  [LLM] backend={label} model={model} url={url}")

    response = None
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=LLM_REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        body = response.json()
        choices = body.get("choices") if isinstance(body, dict) else None
        first = choices[0] if choices else None
        message = first.get("message", {}) if isinstance(first, dict) else {}
        content = message.get("content", "") if isinstance(message, dict) else ""
        if not isinstance(content, str) or not content.strip():
            print(f"Ошибка LLM обработки [{label}]: пустой content в ответе")
            return {"clean_title": original_title, "year": None, "tmdb_queries": [original_title, title]}
        parsed = _parse_json_object(content)
        if parsed is None:
            print(f"Ошибка LLM обработки [{label}]: не JSON в ответе: {content[:500]}")
            return {"clean_title": original_title, "year": None, "tmdb_queries": [original_title, title]}
        data = _normalize_llm_data(parsed, original_title, title)
        if data != parsed:
            print(f"  [LLM] ответ нормализован: {data}")
        return data
    except requests.exceptions.HTTPError as e:
        status = response.status_code if response is not None else "?"
        body = (response.text or "")[:2000] if response is not None else ""
        detail = ""
        if response is not None:
            try:
                err_json = response.json()
                if isinstance(err_json, dict):
                    err = err_json.get("error")
                    if isinstance(err, dict):
                        detail = str(err.get("message", ""))[:2000]
                    elif isinstance(err, str):
                        detail = err[:2000]
                    elif "message" in err_json:
                        detail = str(err_json.get("message", ""))[:2000]
            except ValueError:
                pass
        print(f"Ошибка LLM обработки [{label}]: HTTP {status} for url {url}: {e}")
        if detail:
            print(f"  {label} error.message: {detail}")
        if body:
            print(f"  {label} body: {body}")
        return {"clean_title": original_title, "year": None, "tmdb_queries": [original_title, title]}
    except Exception as e:
        print(f"Ошибка LLM обработки [{label}]: {e}")
        return {"clean_title": original_title, "year": None, "tmdb_queries": [original_title, title]}


def step3_and_4_tmdb_and_validate(llm_data: dict, original_plot: str, threshold: float = 0.6, provider: LLMProvider | None = None, title: str = "", original_title: str = "") -> int | None:
    """
    ШАГ 3 и 4: Поиск по чистым запросам в TMDb и валидация сюжета.
    Поиск — по исходным названиям + запросам LLM, на ru-RU и en-US, слияние по id.
    Год используется только для ранжирования кандидатов, а не для фильтра.
    Если год кандидата расходится с годом LLM больше чем на 1 — требуем
    сюжет >= PLOT_STRICT_THRESHOLD. Вердикт — аргмакс по скорам топа,
    без раннего return: PLOT_WIN_MARGIN решает, нужен ли тай-брейк по рангу.
    provider: None (= ACTIVE_PROVIDER).
    """
    queries = llm_data.get("tmdb_queries", []) or []
    clean_title = llm_data.get("clean_title", "") or ""
    llm_year = _coerce_year(llm_data.get("year"))

    # --- ШАГ 3: сбор кандидатов без фильтра по году, ru + en ---
    # Чистим запросы: TMDB не понимает год внутри query, а LLM его туда клеит.
    # Исходные названия добавляем всегда — страховка на случай капризов LLM.
    searched: list = []
    for raw in [original_title, title, *queries]:
        cleaned = _clean_tmdb_query(raw)
        if not cleaned:
            continue
        if cleaned in searched:
            print(f"  [TMDb] запрос '{raw}': дубль, пропускаю")
            continue
        if cleaned != str(raw or "").strip():
            print(f"  [TMDb] запрос '{raw}' -> очищен '{cleaned}'")
        searched.append(cleaned)

    merged: dict = {}  # tmdb_id -> record
    for qi, query in enumerate(searched):
        for lang in ("ru-RU", "en-US"):
            url = "https://api.themoviedb.org/3/search/movie"
            params = {
                "api_key": TMDB_API_KEY,
                "query": query,
                "language": lang
            }

            try:
                print(f"  [TMDb] запрос '{query}' [{lang}]")
                resp = requests.get(url, params=params, timeout=5)
                res = resp.json()
                if "results" not in res:
                    print(f"  [TMDb] запрос '{query}' [{lang}]: ошибка API http={resp.status_code} body={str(res)[:500]}")
                    continue
                results = res.get("results", [])
                print(f"  [TMDb] запрос '{query}' [{lang}] -> кандидатов: {len(results)}")
                overview_key = "overview_ru" if lang == "ru-RU" else "overview_en"
                for pos, movie in enumerate(results):
                    movie_id = movie.get("id")
                    rec = merged.get(movie_id)
                    if rec is None:
                        rec = {
                            "id": movie_id,
                            "title": movie.get("title", ""),
                            "original_title": movie.get("original_title", ""),
                            "alt_titles": [],
                            "overview_ru": "",
                            "overview_en": "",
                            "release_date": movie.get("release_date"),
                            "qi": qi,
                            "pos": pos,
                        }
                        merged[movie_id] = rec
                    for variant in (movie.get("title", ""), movie.get("original_title", "")):
                        if variant and variant not in rec["alt_titles"] and variant != rec["title"] and variant != rec["original_title"]:
                            rec["alt_titles"].append(variant)
                    overview = movie.get("overview", "") or ""
                    if overview and not rec[overview_key]:
                        rec[overview_key] = overview
            except Exception as e:
                print(f"Ошибка TMDb API: {e}")

    if not merged:
        print("  [TMDb] итог: кандидаты не найдены")
        return None

    collected = [
        ({
            "id": rec["id"],
            "title": rec["title"],
            "original_title": rec["original_title"],
            "_alt_titles": rec["alt_titles"],
            "overview": rec["overview_ru"],
            "_en_overview": rec["overview_en"],
            "release_date": rec["release_date"],
        }, rec["qi"], rec["pos"])
        for rec in merged.values()
    ]

    # --- Ранжирование по дешёвым признакам (название, год) ---
    ranked = _rank_candidates(collected, clean_title, llm_year)
    top_n = min(MAX_PLOT_VALIDATIONS, len(ranked))
    print(f"  [TMDb] ранжировано {len(ranked)}, проверяю топ-{top_n} (год LLM={llm_year})")

    # --- ШАГ 4: скоринг всего топа, без раннего return ---
    scored: list = []  # dicts: movie/movie_id/score/eff/tb/yb/order
    for order, (movie, title_bonus, year_bonus) in enumerate(ranked[:MAX_PLOT_VALIDATIONS]):
        movie_id = movie.get("id")
        cand_year = _release_year(movie.get("release_date"))
        if llm_year is not None and cand_year is not None and abs(cand_year - llm_year) > 1:
            eff_threshold = PLOT_STRICT_THRESHOLD
            print(f"  [TMDb] ID {movie_id}: год расходится (LLM={llm_year}, TMDB={cand_year}) — требую сюжет >= {eff_threshold:.2f}")
        else:
            eff_threshold = threshold

        tmdb_overview = movie.get("overview", "") or movie.get("_en_overview", "")
        used_lang = "ru" if movie.get("overview", "") else "en"
        print(f"  [TMDb] Проверка ID {movie_id}: '{movie.get('title')}' ({movie.get('original_title')}, {movie.get('release_date')}) бонусы title={title_bonus} year={year_bonus} overview_len={len(tmdb_overview or '')} lang={used_lang}")

        # Запасной запрос сюжета на английском, если на русском пусто
        if not tmdb_overview:
            try:
                print(f"  [TMDb] ID {movie_id}: overview пуст, запрашиваю en-US...")
                en_res = requests.get(
                    f"https://api.themoviedb.org/3/movie/{movie_id}",
                    params={"api_key": TMDB_API_KEY, "language": "en-US"},
                    timeout=5
                ).json()
                tmdb_overview = en_res.get("overview", "")
                print(f"  [TMDb] ID {movie_id}: en overview_len={len(tmdb_overview or '')} preview={((tmdb_overview or '')[:120])!r}")
            except Exception as e:
                print(f"Ошибка TMDb API: {e}")
                continue

        if not (tmdb_overview or "").strip():
            print(f"  [TMDb] ID {movie_id}: пропуск сравнения — overview пуст в обеих локалях")
            continue

        score = compare_plots(original_plot, tmdb_overview, provider=provider)
        print(f"  [TMDb] Проверка ID {movie_id}: '{movie.get('title')}' -> Совпадение сюжета: {score:.2f} (порог {eff_threshold:.2f})")
        scored.append({
            "movie": movie, "movie_id": movie_id, "score": score,
            "eff": eff_threshold, "tb": title_bonus, "yb": year_bonus,
            "order": order,
        })

    contenders = [s for s in scored if s["score"] >= s["eff"]]
    if not contenders:
        print(f"  [TMDb] итог: проверено {len(scored)} из {len(ranked)} кандидатов, порог никто не взял")
        return None

    # --- Аргмакс + margin ---
    print("  [TMDb] претенденты (score/порог/бонусы): " + ", ".join(
        f"{c['movie_id']}={c['score']:.2f}/{c['eff']:.2f}/t{c['tb']}y{c['yb']}" for c in contenders
    ))
    winner_id = _pick_winner(contenders)
    print(f"  -> ФИЛЬМ ПОДТВЕРЖДЕН! ID: {winner_id}")
    return winner_id


def _pick_winner(contenders: list) -> int:
    """Аргмакс по скорам; при зазоре < PLOT_WIN_MARGIN — тай-брейк по бонусам ранга."""
    ordered = sorted(contenders, key=lambda s: -s["score"])  # stable: равные скоры сохраняют порядок ранга
    if len(ordered) == 1:
        print(f"  [TMDb] единственный претендент: ID {ordered[0]['movie_id']}")
        return ordered[0]["movie_id"]

    top, runner = ordered[0], ordered[1]
    gap = top["score"] - runner["score"]
    if gap >= PLOT_WIN_MARGIN:
        print(f"  [TMDb] зазор {gap:.2f} >= {PLOT_WIN_MARGIN:.2f} — побеждает ID {top['movie_id']}")
        return top["movie_id"]

    cluster = [c for c in ordered if top["score"] - c["score"] < PLOT_WIN_MARGIN]
    cluster.sort(key=lambda c: (-(c["tb"] + c["yb"]), c["order"]))
    winner = cluster[0]
    print(f"  [TMDb] зазор мал ({gap:.2f} < {PLOT_WIN_MARGIN:.2f}), выбран по рангу: ID {winner['movie_id']} "
          f"(бонусы title={winner['tb']} year={winner['yb']}) среди {','.join(str(c['movie_id']) for c in cluster)}")
    return winner["movie_id"]


def run_pipeline(filename: str, provider: LLMProvider | None = None) -> int | None:
    filepath = os.path.join("test_movies", filename)
    if not os.path.exists(filepath):
        print(f"Файл {filepath} не найден!")
        return None

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    title = data.get("title", "")
    original_title = data.get("original_title", "")
    plot = data.get("plot", "")
    expected_id = data.get("tmdbid")

    print(f"\n--- Старт обработки: {filename} ---")

    print("1. Поиск информации в вебе (Tavily)...")
    web_context = step1_search_web(title, original_title)

    print("2. Извлечение чистых данных через LLM...")
    llm_data = step2_extract_data_with_llm(title, original_title, plot, web_context, provider=provider)
    print(f"   Результат LLM: {llm_data}")

    print("3 & 4. Поиск на TMDb и сверка сюжетов...")
    found_id = step3_and_4_tmdb_and_validate(llm_data, plot, provider=provider, title=title, original_title=original_title)

    print("-" * 40)
    if expected_id is not None:
        if found_id == int(expected_id):
            print(f"УСПЕХ: Найден верный ID ({found_id})")
        else:
            print(f"ОШИБКА: Ожидался {expected_id}, но найден {found_id}")
    else:
        print(f"Результат пайплайна: ID {found_id}")
    return found_id


def run_all(provider: LLMProvider | None = None) -> dict:
    """Прогон по всем test_movies/*.json с компактной сводкой НАЗВАНИЕ - ОК/НЕ ОК."""
    files = sorted(glob.glob(os.path.join("test_movies", "*.json")))
    if not files:
        print("В test_movies/*.json файлов нет!")
        return {}

    verdicts: list = []  # (filename, ok)
    for filepath in files:
        filename = os.path.basename(filepath)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                expected = json.load(f).get("tmdbid")
        except Exception as e:
            print(f"\n{filename} - НЕ ОК (файл не читается: {e})")
            verdicts.append((filename, False))
            continue
        found = run_pipeline(filename, provider=provider)
        ok = expected is not None and found == int(expected)
        verdicts.append((filename, ok))
        if ok:
            print(f"{filename} - ОК")
        else:
            print(f"{filename} - НЕ ОК (ожидался {expected}, найден {found})")

    print("-" * 40)
    good = sum(1 for _, ok in verdicts if ok)
    for filename, ok in verdicts:
        print(f"{filename} - {'ОК' if ok else 'НЕ ОК'}")
    print(f"ИТОГ: {good}/{len(verdicts)}")
    return dict(verdicts)


if __name__ == "__main__":
    names = sys.argv[1:]
    if names:
        for name in names:
            run_pipeline(name)
    else:
        run_all()