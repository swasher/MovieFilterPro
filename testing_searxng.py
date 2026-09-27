"""Standalone-сравнение веб-поиска для умного поиска TMDB: Tavily vs локальный SearXNG.

Ничего в приложении не меняет: только читает dev-БД и настройки (читает, не пишет),
делает GET-запросы к SearXNG и вызовы Tavily/локального AI.

Запуск (из корня проекта):
    uv run python testing_searxng.py                          # 3 фильма из БД, оба провайдера
    uv run python testing_searxng.py --limit 5                # больше кейсов
    uv run python testing_searxng.py --movie-id 123           # конкретный фильм
    uv run python testing_searxng.py --demo                   # встроенные кейсы (без БД)
    uv run python testing_searxng.py --provider searxng       # только SearXNG
    uv run python testing_searxng.py --ai                     # + прогон локального AI (extract_web_hints)
    uv run python testing_searxng.py --dump .tmp_searxng      # сохранить полные контексты в папку
    uv run python testing_searxng.py --url http://localhost:8087/search
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass

# Адрес инстанса SearXNG по умолчанию; переопределяется --url или Preferences.searxng_url
DEFAULT_SEARXNG_URL = "http://localhost:8087/search"

SEARXNG_TIMEOUT_SECONDS = 25
SEARXNG_LANGUAGE_DEFAULT = "ru-RU"
PREVIEW_CHARS = 900
UA = "MovieFilterPro-testing/1.0"

SEARXNG_JSON_HINT = (
    "Похоже, в инстансе SearXNG выключен JSON-формат (или запрос отбит лимитером).\n"
    "Добавь в settings.yml инстанса:\n"
    "  search:\n"
    "    formats:\n"
    "      - html\n"
    "      - json\n"
    "и перезапусти SearXNG. Ручная проверка: <url>?q=test&format=json"
)


@dataclass(slots=True)
class SearchCase:
    label: str
    title: str
    original_title: str
    plot: str
    year: int | None = None


@dataclass(slots=True)
class ProviderResult:
    provider: str
    ok: bool
    context: str = ""
    elapsed: float = 0.0
    error: str = ""
    notes: tuple[str, ...] = ()


# Встроенные кейсы (используются с --demo или если БД недоступна).
# Кейс из исходной заготовки: намеренно искажённые данные (название не бьётся с сюжетом).
DEMO_CASES = (
    SearchCase(
        label="demo: искажённые данные",
        title="Голдфингер (Золотой палец)",
        original_title="",
        plot=(
            "Среди крупных бизнесменов и криминальных авторитетов Гонконга появляется "
            "незнакомец, который выделяется дерзостью в общении и смелостью бизнес-планов."
        ),
        year=2023,
    ),
)


# --------------------------------------------------------------------------- #
#                       Вспомогательное: данные и вывод                       #
# --------------------------------------------------------------------------- #


def _setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "movie_filter_pro.settings")
    import django

    django.setup()


def collect_db_cases(limit: int, movie_id: int | None = None) -> list[SearchCase]:
    """Читает фильмы из dev-БД (только SELECT, ничего не пишет)."""
    from vault.models import Movie

    qs = Movie.objects.exclude(description__isnull=True).exclude(description="")
    if movie_id is not None:
        qs = qs.filter(pk=movie_id)
    qs = qs.only("id", "title", "original_title", "year", "description").order_by("id")

    cases: list[SearchCase] = []
    for movie in qs.iterator():
        plot = (movie.description or "").strip()
        if len(plot) < 40:  # SMART_MIN_PLOT_CHARS: короче — умный поиск не запускается
            continue
        cases.append(
            SearchCase(
                label=f"db id={movie.id}",
                title=movie.title or "",
                original_title=movie.original_title or "",
                plot=plot,
                year=movie.year,
            )
        )
        if len(cases) >= limit:
            break
    return cases


def build_queries(case: SearchCase) -> list[tuple[str, str]]:
    """Повторяет построение запросов из WebSearchService (чтобы сравнение было честным)."""
    from vault.services.web_search_service import WebSearchService

    return WebSearchService._build_queries(case.title, case.original_title, case.plot)


def print_section(title: str, symbol: str = "=") -> None:
    width = 78
    print(f"\n{symbol * width}")
    print(f" {title}")
    print(f"{symbol * width}")


def _preview(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= PREVIEW_CHARS:
        return text
    return text[:PREVIEW_CHARS].rstrip() + "\n[...обрезано, полный текст см. --dump]"


def print_provider_result(result: ProviderResult) -> None:
    header = result.provider.upper()
    if not result.ok:
        print(f"--- {header}: ОШИБКА ({result.elapsed:.2f}s) ---")
        print(result.error)
        return
    print(
        f"--- {header}: OK | {result.elapsed:.2f}s | context_chars={len(result.context)} ---"
    )
    for note in result.notes:
        print(f"[i] {note}")
    print(_preview(result.context))


# --------------------------------------------------------------------------- #
#                                 Провайдеры                                  #
# --------------------------------------------------------------------------- #


def run_tavily(case: SearchCase) -> ProviderResult:
    from vault.services.web_search_service import WebSearchService

    if not WebSearchService.get_tavily_api_key():
        return ProviderResult(
            "tavily", False,
            error="Tavily API key не настроен (только Preferences: UserPreferences.tavily_api_key)",
        )
    t0 = time.perf_counter()
    try:
        context = WebSearchService.search_web_via_tavily(case.title, case.original_title, case.plot)
    except Exception as exc:
        return ProviderResult(
            "tavily", False, elapsed=time.perf_counter() - t0,
            error=f"{type(exc).__name__}: {exc}",
        )
    return ProviderResult("tavily", True, context=context, elapsed=time.perf_counter() - t0)


def _format_unresponsive(items: object) -> str:
    parts: list[str] = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            parts.append(f"{item[0]}: {item[1]}")
        else:
            parts.append(str(item))
    return "; ".join(parts)[:300]


def run_searxng(case: SearchCase, url: str, language: str, timeout: float) -> ProviderResult:
    import requests

    from vault.services.web_search_service import WebSearchService

    t0 = time.perf_counter()
    context = ""
    notes: list[str] = []
    queries = build_queries(case)

    for label, query in queries:
        params: dict[str, str] = {"q": query, "format": "json"}
        if language:
            params["language"] = language
        try:
            response = requests.get(
                url, params=params, headers={"User-Agent": UA}, timeout=timeout
            )
        except requests.RequestException as exc:
            return ProviderResult(
                "searxng", False, elapsed=time.perf_counter() - t0,
                error=f"{type(exc).__name__}: {exc}\nПроверь, что SearXNG запущен и {url} доступен.",
            )

        if response.status_code == 403:
            return ProviderResult(
                "searxng", False, elapsed=time.perf_counter() - t0,
                error=f"HTTP 403 Forbidden.\n{SEARXNG_JSON_HINT}",
            )
        if response.status_code != 200:
            return ProviderResult(
                "searxng", False, elapsed=time.perf_counter() - t0,
                error=f"HTTP {response.status_code}: {response.text[:300]}",
            )
        try:
            payload = response.json()
        except ValueError:
            return ProviderResult(
                "searxng", False, elapsed=time.perf_counter() - t0,
                error=f"Ответ не JSON: {response.text[:300]}\n{SEARXNG_JSON_HINT}",
            )

        unresponsive = _format_unresponsive(payload.get("unresponsive_engines"))
        if unresponsive:
            notes.append(f"unresponsive_engines: {unresponsive}")

        results = payload.get("results") or []
        if not results:
            notes.append(f"пустая выдача по запросу «{label}»")
        context += f"--- Поиск по {label} ---\n"
        for result in results[: WebSearchService.MAX_RESULTS]:
            title = (result.get("title") or "").strip()
            content = (result.get("content") or result.get("url") or "").strip()
            context += f"Заголовок: {title}\nКонтент: {content}\n\n"

    return ProviderResult("searxng", True, context=context, elapsed=time.perf_counter() - t0, notes=tuple(notes))


def probe_searxng(url: str, language: str, timeout: float) -> bool:
    """Быстрая проба: доступен ли JSON-формат и жив ли инстанс."""
    import requests

    print_section("ПРОБА SEARXNG")
    print(f"URL: {url} | language={language or 'all'}")
    params: dict[str, str] = {"q": "probe", "format": "json"}
    if language:
        params["language"] = language
    try:
        response = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=timeout)
    except requests.RequestException as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        return False
    if response.status_code != 200:
        print(f"[FAIL] HTTP {response.status_code}: {response.text[:300]}")
        if response.status_code == 403:
            print(SEARXNG_JSON_HINT)
        return False
    try:
        payload = response.json()
    except ValueError:
        print(f"[FAIL] Ответ не JSON: {response.text[:300]}")
        print(SEARXNG_JSON_HINT)
        return False
    version = payload.get("version") or "?"
    results = payload.get("results") or []
    print(f"[OK] version={version} | results={len(results)}")
    unresponsive = _format_unresponsive(payload.get("unresponsive_engines"))
    if unresponsive:
        print(f"[i] unresponsive_engines: {unresponsive}")
    return True


# --------------------------------------------------------------------------- #
#                          Локальный AI (опционально)                          #
# --------------------------------------------------------------------------- #


def run_ai_hints(case: SearchCase, context: str) -> tuple[dict | None, str]:
    from vault.services.tmdb_ai_matching_service import TMDBAIMatchingService
    from vault.services.tmdb_smart_search_service import is_local_ai_available

    if not (context or "").strip():
        return None, "пустой контекст — AI нечего разбирать"
    if not is_local_ai_available():
        return None, "локальный AI выключен (Preferences: ai_enabled + ai_base_url + ai_model)"
    t0 = time.perf_counter()
    hints = TMDBAIMatchingService.extract_web_hints(
        title=case.title,
        original_title=case.original_title,
        plot=case.plot,
        web_context=context,
    )
    elapsed = time.perf_counter() - t0
    if hints is None:
        return None, f"AI не вернул распознанный JSON ({elapsed:.2f}s)"
    return hints, f"OK ({elapsed:.2f}s)"


def print_hints(label: str, hints: dict | None, status: str) -> None:
    if hints is None:
        print(f"  {label}: — | {status}")
        return
    print(f"  {label}: {status}")
    print(f"    clean_title: {hints.get('clean_title')!r}")
    print(f"    year:        {hints.get('year')}")
    print(f"    queries:     {json.dumps(hints.get('tmdb_queries') or [], ensure_ascii=False)}")


# --------------------------------------------------------------------------- #
#                                    CLI                                      #
# --------------------------------------------------------------------------- #


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standalone-сравнение Tavily и локального SearXNG для умного поиска TMDB."
    )
    parser.add_argument("--url", default=None, help="URL SearXNG /search (по умолчанию из Preferences.searxng_url)")
    parser.add_argument(
        "--provider", choices=("both", "tavily", "searxng"), default="both",
        help="кого гонять (по умолчанию оба)",
    )
    parser.add_argument("--limit", type=int, default=3, help="сколько фильмов взять из БД")
    parser.add_argument("--movie-id", type=int, default=None, help="конкретный Movie.id вместо выборки")
    parser.add_argument("--demo", action="store_true", help="встроенные кейсы вместо фильмов из БД")
    parser.add_argument("--ai", action="store_true", help="прогнать контексты через extract_web_hints")
    parser.add_argument(
        "--language", default=SEARXNG_LANGUAGE_DEFAULT,
        help="язык SearXNG (ru-RU, en-US, all); пустая строка — не передавать параметр",
    )
    parser.add_argument("--timeout", type=float, default=SEARXNG_TIMEOUT_SECONDS, help="таймаут SearXNG, сек")
    parser.add_argument("--dump", default="", help="папка для сохранения полных контекстов")
    return parser.parse_args()


def _dump_result(dump_dir: str, index: int, result: ProviderResult) -> None:
    import pathlib

    path = pathlib.Path(dump_dir)
    path.mkdir(parents=True, exist_ok=True)
    target = path / f"case{index}_{result.provider}.txt"
    body = result.context if result.ok else f"[ERROR] {result.error}"
    target.write_text(body, encoding="utf-8")


def main() -> int:
    args = parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    language = (args.language or "").strip()

    django_ready = True
    try:
        _setup_django()
    except Exception as exc:
        django_ready = False
        print(f"[!] Django setup failed: {exc}")

    # URL: --url важнее Preferences, Preferences важнее localhost-заглушки
    searxng_url = (args.url or "").strip()
    if not searxng_url and django_ready:
        from vault.services.web_search_service import WebSearchService

        searxng_url = WebSearchService.get_searxng_url()
    if not searxng_url:
        searxng_url = DEFAULT_SEARXNG_URL

    if args.demo or not django_ready:
        if not args.demo:
            print("[!] БД недоступна — использую demo-кейсы.")
        cases = list(DEMO_CASES)
    else:
        try:
            cases = collect_db_cases(args.limit, args.movie_id)
        except Exception as exc:
            print(f"[!] Не удалось получить фильмы из БД ({exc}) — использую demo-кейсы.")
            cases = list(DEMO_CASES)

    if not cases:
        print("[!] Нет кейсов с описанием >= 40 символов. Попробуй --demo или --movie-id.")
        return 2

    run_tavily_flag = args.provider in ("both", "tavily")
    run_searxng_flag = args.provider in ("both", "searxng")

    if run_searxng_flag:
        probe_searxng(searxng_url, language, args.timeout)

    failures = 0
    for index, case in enumerate(cases, 1):
        print_section(f"КЕЙС #{index}: {case.label}")
        print(f"Title: {case.title!r} | Original: {case.original_title!r} | Year: {case.year}")
        print(f"Plot: {case.plot[:200]}{'...' if len(case.plot) > 200 else ''}")

        results: dict[str, ProviderResult] = {}
        if run_tavily_flag:
            results["tavily"] = run_tavily(case)
            print_provider_result(results["tavily"])
            if args.dump:
                _dump_result(args.dump, index, results["tavily"])
        if run_searxng_flag:
            results["searxng"] = run_searxng(case, searxng_url, language, args.timeout)
            print_provider_result(results["searxng"])
            if args.dump:
                _dump_result(args.dump, index, results["searxng"])
        failures += sum(1 for r in results.values() if not r.ok)

        if args.ai:
            print("--- ЛОКАЛЬНЫЙ AI: extract_web_hints ---")
            hints_by_provider: dict[str, dict | None] = {}
            for name, result in results.items():
                hints, status = run_ai_hints(case, result.context if result.ok else "")
                hints_by_provider[name] = hints
                print_hints(name, hints, status)
            if len(hints_by_provider) == 2 and all(hints_by_provider.values()):
                left = hints_by_provider.get("tavily") or {}
                right = hints_by_provider.get("searxng") or {}
                same_title = (left.get("clean_title") or "") == (right.get("clean_title") or "")
                same_year = left.get("year") == right.get("year")
                print(f"  Вердикт: clean_title совпадает: {'ДА' if same_title else 'НЕТ'} | year совпадает: {'ДА' if same_year else 'НЕТ'}")

    print_section("ИТОГ")
    print(f"Кейсов: {len(cases)} | провайдер: {args.provider} | ошибок: {failures}")
    if not run_tavily_flag:
        print("[i] Tavily не запускался (--provider).")
    if args.ai:
        print("[i] Смотри вердикт по clean_title/year выше: это то, что реально уходит в TMDB-поиск.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
