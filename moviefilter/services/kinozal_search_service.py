from __future__ import annotations

from dataclasses import dataclass, field

from bs4 import BeautifulSoup
from requests import RequestException

from core.models import UserPreferences
from kinozal_scan.parse import parse_header
from moviefilter.classes import KinozalSearch
from moviefilter.kinozal import KinozalClient, LinkConstructor, normalize_kinozal_domain

# Качество видео в терминах Kinozal (параметр v в browse.php).
QUALITY_4K = 7
QUALITY_HD = 3


@dataclass(slots=True, frozen=True)
class KinozalSearchResult:
    items: list[KinozalSearch] = field(default_factory=list)


class KinozalSearchError(Exception):
    """Ошибка поиска раздач на Kinozal с кодом для API-слоя."""

    def __init__(self, code: str, message: str, *, hint: str | None = None, status_code: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.status_code = status_code


def parse_search_rows(response, quality: int, preferences: UserPreferences | None = None) -> list[KinozalSearch]:
    """
    Парсит строки раздач со страницы поиска Kinozal (browse.php?s=...).

    Каждой строке дополнительно проставляются title/original_title/year,
    распарсенные из заголовка релиза (нужны для импорта в Vault).
    """
    preferences = preferences or UserPreferences.get()
    domain = normalize_kinozal_domain(preferences.kinozal_domain)

    soup = BeautifulSoup(response.content, "html.parser")
    results: list[KinozalSearch] = []
    for element in soup.find_all("tr", "bg"):
        item = KinozalSearch()
        item.id = int(element.a["href"].split("=")[1])
        item.header = element.a.text
        item.size = element.find_all("td", "s")[1].text
        item.seed = element.find("td", {"class": "sl_s"}).text
        item.peer = element.find("td", {"class": "sl_p"}).text
        item.created = element.find_all("td", "s")[2].text
        item.link = f"https://{domain}{element.a['href']}"
        item.is_4k = quality == QUALITY_4K
        item.is_sdr = "SDR" in item.header
        item.title, item.original_title, item.year = parse_header(item.header)
        results.append(item)

    return results


def _fetch_page(client: KinozalClient, builder: LinkConstructor) -> list[KinozalSearch]:
    try:
        response = client.get_html_response(builder.search_url())
    except RequestException as exc:
        raise KinozalSearchError(
            "kinozal_unreachable",
            "Не удалось получить результаты поиска с Kinozal.",
            hint=str(exc),
        ) from exc
    if not response.ok:
        raise KinozalSearchError(
            "kinozal_search_failed",
            f"Kinozal search failed with status {response.status_code}.",
        )
    return parse_search_rows(response, builder.v)


def search_releases(query: str, year: str | None, quality: str) -> KinozalSearchResult:
    """
    Поиск раздач на Kinozal по названию/году.

    quality:
      '4k' — сначала ищем 4K (v=7); если ничего не нашлось, автоматически
            повторяем поиск в HD (v=3).
      'hd' — только HD.

    Домен зеркала берётся из UserPreferences через LinkConstructor.
    """
    client = KinozalClient()

    try_qualities = [QUALITY_4K, QUALITY_HD] if quality == "4k" else [QUALITY_HD]
    for v in try_qualities:
        kwargs = {"s": query, "v": v}
        if year:
            kwargs["d"] = year
        items = _fetch_page(client, LinkConstructor(**kwargs))
        if items or v == try_qualities[-1]:
            return KinozalSearchResult(items=items)

    return KinozalSearchResult(items=[])
