from __future__ import annotations

import logging

logger = logging.getLogger("vault.tmdb_sync")


class WebSearchError(RuntimeError):
    """Веб-поиск не работает: очередь TMDB sync должна остановиться, а не молча продолжать."""


# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #


class WebSearchService:
    """Провайдер-агностик веб-поиск для умного поиска TMDB.

    Приоритет: локальный SearXNG (UserPreferences.searxng_url), иначе Tavily
    (UserPreferences.tavily_api_key). Настройки берутся ТОЛЬКО из Preferences —
    без fallback на *_API_KEY/*_URL в .env (см. правило в AGENTS.md).

    В отличие от старого find_tmdb_id.py ошибки НЕ глотаются: любой сбой
    поднимает WebSearchError (алиас TavilySearchError), чтобы очередь
    остановилась с красным тостом.
    """

    PLOT_FRAGMENT_CHARS = 500
    MAX_RESULTS = 5
    TAVILY_SEARCH_DEPTH = "basic"

    SEARXNG_TIMEOUT_SECONDS = 20
    SEARXNG_LANGUAGE = "ru-RU"

    PROVIDER_SEARXNG = "searxng"
    PROVIDER_TAVILY = "tavily"

    @classmethod
    def get_tavily_api_key(cls) -> str:
        """Tavily ключ: только UserPreferences.tavily_api_key."""
        try:
            from moviefilter.models import UserPreferences

            return (UserPreferences.get().tavily_api_key or "").strip()
        except Exception:
            logger.debug("Tavily prefs lookup failed", exc_info=True)
            return ""

    @classmethod
    def get_searxng_url(cls) -> str:
        """SearXNG URL: только UserPreferences.searxng_url."""
        try:
            from moviefilter.models import UserPreferences

            return (UserPreferences.get().searxng_url or "").strip()
        except Exception:
            logger.debug("SearXNG prefs lookup failed", exc_info=True)
            return ""

    @classmethod
    def get_provider(cls) -> str:
        """Активный провайдер: SearXNG имеет приоритет над Tavily. '' — ничего не настроено."""
        if cls.get_searxng_url():
            return cls.PROVIDER_SEARXNG
        if cls.get_tavily_api_key():
            return cls.PROVIDER_TAVILY
        return ""

    @classmethod
    def provider_label(cls) -> str:
        provider = cls.get_provider()
        if provider == cls.PROVIDER_SEARXNG:
            return "SearXNG"
        if provider == cls.PROVIDER_TAVILY:
            return "Tavily"
        return "не настроен"

    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.get_provider())

    @classmethod
    def search_web(cls, title: str, original_title: str, plot: str = "") -> str:
        """ШАГ 1 (урок find_tmdb_id.py): поиск в вебе по названиям и фрагменту сюжета.

        Два запроса: по названиям и по фрагменту сюжета (самый дискриминативный
        сигнал). Возвращает собранный веб-контекст строкой. Провайдер выбирается
        автоматически: SearXNG, если задан его URL, иначе Tavily.
        """
        provider = cls.get_provider()
        if provider == cls.PROVIDER_SEARXNG:
            return cls.search_web_via_searxng(title, original_title, plot)
        if provider == cls.PROVIDER_TAVILY:
            return cls.search_web_via_tavily(title, original_title, plot)
        raise WebSearchError(
            "Веб-поиск не настроен: заполни SearXNG URL или Tavily API key в Preferences"
        )

    @classmethod
    def search_web_via_tavily(cls, title: str, original_title: str, plot: str = "") -> str:
        """Принудительно Tavily (нужен для сравнения/тестов; основной вход — search_web)."""
        api_key = cls.get_tavily_api_key()
        if not api_key:
            raise WebSearchError("Tavily API key не настроен (UserPreferences.tavily_api_key)")

        queries = cls._build_queries(title, original_title, plot)

        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)

        web_context = ""
        for label, query in queries:
            try:
                response = client.search(
                    query=query,
                    search_depth=cls.TAVILY_SEARCH_DEPTH,
                    max_results=cls.MAX_RESULTS,
                )
            except Exception as exc:
                logger.error("WEB_SEARCH_FAILED | provider=tavily | label=%s | %s", label, exc)
                raise WebSearchError(f"Tavily веб-поиск ({label}) не сработал: {exc}") from exc
            web_context += f"--- Поиск по {label} ---\n"
            for result in (response or {}).get("results", []) or []:
                web_context += f"Заголовок: {result.get('title')}\nКонтент: {result.get('content')}\n\n"

        cls._log_ok(cls.PROVIDER_TAVILY, len(queries), web_context)
        return web_context

    @classmethod
    def search_web_via_searxng(
        cls,
        title: str,
        original_title: str,
        plot: str = "",
        *,
        url: str | None = None,
    ) -> str:
        """Принудительно SearXNG. url — override для тестов/скриптов сравнения.

        Требует включённый JSON-формат на инстансе (settings.yml:
        search.formats: [html, json]), иначе прилетит 403.
        """
        import requests

        searxng_url = (url or cls.get_searxng_url()).strip()
        if not searxng_url:
            raise WebSearchError("SearXNG URL не настроен (UserPreferences.searxng_url)")

        queries = cls._build_queries(title, original_title, plot)

        web_context = ""
        for label, query in queries:
            params: dict[str, str] = {"q": query, "format": "json"}
            if cls.SEARXNG_LANGUAGE:
                params["language"] = cls.SEARXNG_LANGUAGE
            try:
                response = requests.get(
                    searxng_url, params=params, timeout=cls.SEARXNG_TIMEOUT_SECONDS
                )
            except requests.RequestException as exc:
                logger.error("WEB_SEARCH_FAILED | provider=searxng | label=%s | %s", label, exc)
                raise WebSearchError(f"SearXNG веб-поиск ({label}) не сработал: {exc}") from exc
            if response.status_code == 403:
                logger.error("WEB_SEARCH_FAILED | provider=searxng | label=%s | HTTP 403", label)
                raise WebSearchError(
                    f"SearXNG веб-поиск ({label}): HTTP 403. "
                    "Похоже, на инстансе выключен JSON-формат (settings.yml: search.formats: [html, json])."
                )
            if response.status_code != 200:
                logger.error(
                    "WEB_SEARCH_FAILED | provider=searxng | label=%s | HTTP %s",
                    label,
                    response.status_code,
                )
                raise WebSearchError(
                    f"SearXNG веб-поиск ({label}) вернул HTTP {response.status_code}"
                )
            try:
                payload = response.json()
            except ValueError as exc:
                logger.error("WEB_SEARCH_FAILED | provider=searxng | label=%s | bad json", label)
                raise WebSearchError(
                    f"SearXNG веб-поиск ({label}) вернул не JSON: включён ли format=json на инстансе?"
                ) from exc

            unresponsive = payload.get("unresponsive_engines") or []
            if unresponsive:
                logger.warning(
                    "WEB_SEARCH_ENGINES | provider=searxng | label=%s | unresponsive=%s",
                    label,
                    unresponsive,
                )

            web_context += f"--- Поиск по {label} ---\n"
            for result in (payload.get("results") or [])[: cls.MAX_RESULTS]:
                result_title = (result.get("title") or "").strip()
                content = (result.get("content") or result.get("url") or "").strip()
                web_context += f"Заголовок: {result_title}\nКонтент: {content}\n\n"

        cls._log_ok(cls.PROVIDER_SEARXNG, len(queries), web_context)
        return web_context

    @classmethod
    def _build_queries(cls, title: str, original_title: str, plot: str) -> list[tuple[str, str]]:
        """Два запроса: названия и фрагмент сюжета (общие для всех провайдеров)."""
        name_parts: list[str] = []
        for part in (title, original_title):
            part = (part or "").strip()
            if part and part not in name_parts:
                name_parts.append(part)
        queries = [("название", f"{' '.join(name_parts)} movie film")]
        fragment = cls._clip_plot(plot, cls.PLOT_FRAGMENT_CHARS)
        if fragment:
            queries.append(("сюжет", f"{fragment} movie film"))
        return queries

    @classmethod
    def _log_ok(cls, provider: str, query_count: int, web_context: str) -> None:
        logger.info(
            "WEB_SEARCH_OK | provider=%s | queries=%s | context_chars=%s",
            provider,
            query_count,
            len(web_context),
        )

    # ------------------------------------ #
    #            DOMAIN LAYER              #
    # ------------------------------------ #

    @staticmethod
    def _clip_plot(value: str, max_chars: int) -> str:
        text = (value or "").strip()
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars].rstrip()}..."
