from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger("vault.tmdb_sync")


class TavilySearchError(RuntimeError):
    """Tavily веб-поиск не работает: очередь TMDB sync должна остановиться, а не молча продолжать."""


# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #


class TavilyService:
    """Клиент Tavily веб-поиска для умного поиска TMDB.

    Ключ читается из UserPreferences.tavily_api_key (основной источник, прод).
    TAVILY_API_KEY из settings (.env) оставлен только как legacy/dev-fallback —
    по той же схеме, что OMDBService.get_api_key.

    В отличие от старого find_tmdb_id.py ошибки НЕ глотаются: любой сбой
    поднимает TavilySearchError, чтобы очередь остановилась с красным тостом.
    """

    PLOT_FRAGMENT_CHARS = 500
    SEARCH_DEPTH = "basic"
    MAX_RESULTS = 5

    @classmethod
    def get_api_key(cls) -> str:
        """Tavily ключ: сначала UserPreferences, затем legacy settings (.env)."""
        try:
            from moviefilter.models import UserPreferences

            prefs_key = (UserPreferences.get().tavily_api_key or "").strip()
            if prefs_key:
                return prefs_key
        except Exception:
            logger.debug("Tavily prefs lookup failed, fallback to settings", exc_info=True)
        return (getattr(settings, "TAVILY_API_KEY", "") or "").strip()

    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.get_api_key())

    @classmethod
    def search_web(cls, title: str, original_title: str, plot: str = "") -> str:
        """ШАГ 1 (урок find_tmdb_id.py): поиск в вебе по названиям и фрагменту сюжета.

        Два запроса: по названиям и по фрагменту сюжета (самый дискриминативный
        сигнал). Возвращает собранный веб-контекст строкой.
        """
        api_key = cls.get_api_key()
        if not api_key:
            raise TavilySearchError(
                "TAVILY_API_KEY не настроен (UserPreferences.tavily_api_key или TAVILY_API_KEY в .env)"
            )

        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)

        name_parts: list[str] = []
        for part in (title, original_title):
            part = (part or "").strip()
            if part and part not in name_parts:
                name_parts.append(part)
        queries = [("название", f"{' '.join(name_parts)} movie film")]
        fragment = cls._clip_plot(plot, cls.PLOT_FRAGMENT_CHARS)
        if fragment:
            queries.append(("сюжет", f"{fragment} movie film"))

        web_context = ""
        for label, query in queries:
            if not query.strip():
                continue
            try:
                response = client.search(
                    query=query,
                    search_depth=cls.SEARCH_DEPTH,
                    max_results=cls.MAX_RESULTS,
                )
            except Exception as exc:
                logger.error("TAVILY_SEARCH_FAILED | label=%s | %s", label, exc)
                raise TavilySearchError(f"Tavily веб-поиск ({label}) не сработал: {exc}") from exc
            web_context += f"--- Поиск по {label} ---\n"
            for result in (response or {}).get("results", []) or []:
                web_context += f"Заголовок: {result.get('title')}\nКонтент: {result.get('content')}\n\n"

        logger.info(
            "TAVILY_SEARCH_OK | queries=%s | context_chars=%s",
            len(queries),
            len(web_context),
        )
        return web_context

    # ------------------------------------ #
    #            DOMAIN LAYER              #
    # ------------------------------------ #

    @staticmethod
    def _clip_plot(value: str, max_chars: int) -> str:
        text = (value or "").strip()
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars].rstrip()}..."
