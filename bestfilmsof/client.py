"""HTTP-клиент bestfilmsof.com (DOMAIN/infrastructure layer).

Парсеры и сервисы не знают про transport: получают уже разобранный JSON.
"""

from __future__ import annotations

import requests

from .constants import BASE_URL, PAGE_LIMIT, REQUEST_TIMEOUT


class BestfilmsofError(Exception):
    """Ошибка получения данных с bestfilmsof.com."""


class BestfilmsofClient:
    """Тонкий синхронный клиент JSON API bestfilmsof.com.

    Страницы списка тянем последовательно: origin сайта сериализует
    конкурентные запросы, а выигрыш от параллельности в замерах был ~1.4x.
    """

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: int = REQUEST_TIMEOUT,
        session: requests.Session | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "MovieFilterPro-bestfilmsof/0.1",
                "Accept": "application/json",
            }
        )

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "BestfilmsofClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        try:
            response = self._session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise BestfilmsofError(f"GET {url} failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise BestfilmsofError(f"GET {url} returned non-JSON response") from exc
        if not isinstance(payload, dict):
            raise BestfilmsofError(f"GET {url} returned unexpected payload type")
        return payload

    def fetch_page(
        self,
        year: int,
        genre: str | None = None,
        page: int = 1,
        limit: int = PAGE_LIMIT,
    ) -> dict:
        """Одна страница рейтинга. `genre=None` — весь год без жанра."""
        params: dict[str, int | str] = {"year": year, "page": page, "limit": limit}
        if genre:
            params["genre"] = genre
        return self._get("/api/movies", params=params)

    def fetch_genre_summary(self, genre: str) -> dict:
        """Сводка по жанру: топ-фильм и счётчик для каждого года (1 запрос)."""
        return self._get(f"/api/movies/genre/{genre}")
