from __future__ import annotations

from vault.services.web_search_service import WebSearchError, WebSearchService

# Legacy-совместимость: вся логика веб-поиска переехала в WebSearchService
# (SearXNG-first). TavilySearchError — это WebSearchError (тот же класс),
# поэтому старые `except TavilySearchError` ловят и ошибки SearXNG.
TavilySearchError = WebSearchError


class TavilyService(WebSearchService):
    """DEPRECATED: используй WebSearchService (провайдер-агностик, SearXNG-first).

    Оставлен для обратной совместимости со старыми импортами/тестами и всегда
    работает строго через Tavily (без автопереключения на SearXNG).
    """

    SEARCH_DEPTH = WebSearchService.TAVILY_SEARCH_DEPTH

    @classmethod
    def get_api_key(cls) -> str:
        """Tavily ключ: только UserPreferences.tavily_api_key (fallback в .env удалён)."""
        return cls.get_tavily_api_key()

    @classmethod
    def is_configured(cls) -> bool:
        """Настроен ли именно Tavily (SearXNG проверяет WebSearchService)."""
        return bool(cls.get_tavily_api_key())

    @classmethod
    def search_web(cls, title: str, original_title: str, plot: str = "") -> str:
        """Строго Tavily-поиск (legacy-поведение). Новый код — WebSearchService.search_web."""
        return cls.search_web_via_tavily(title, original_title, plot)
