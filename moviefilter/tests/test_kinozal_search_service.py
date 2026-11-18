from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from moviefilter.classes import KinozalSearch
from moviefilter.services.kinozal_search_service import search_releases


def _row(torrent_id: int) -> KinozalSearch:
    item = KinozalSearch()
    item.id = torrent_id
    return item


class KinozalSearchServiceTests(TestCase):
    @patch("moviefilter.services.kinozal_search_service._fetch_page")
    def test_4k_returns_results_without_fallback(self, fetch_mock):
        fetch_mock.return_value = [_row(1)]

        result = search_releases("Heart of the Beast", "2026", "4k")

        self.assertEqual(len(result.items), 1)
        self.assertEqual(fetch_mock.call_count, 1)
        builder = fetch_mock.call_args[0][1]
        self.assertEqual(builder.v, 7)
        self.assertEqual(builder.s, "Heart of the Beast")
        self.assertEqual(builder.d, "2026")

    @patch("moviefilter.services.kinozal_search_service._fetch_page")
    def test_4k_falls_back_to_hd_when_empty(self, fetch_mock):
        fetch_mock.side_effect = [
            [],  # 4K пусто
            [_row(2)],  # HD нашёлся
        ]

        result = search_releases("Heart of the Beast", None, "4k")

        self.assertEqual(len(result.items), 1)
        self.assertEqual(fetch_mock.call_count, 2)
        self.assertEqual(fetch_mock.call_args_list[0][0][1].v, 7)
        self.assertEqual(fetch_mock.call_args_list[1][0][1].v, 3)
        # Год не указан — параметр d не передаётся в конструктор ссылки.
        self.assertEqual(fetch_mock.call_args_list[0][0][1].d, "")

    @patch("moviefilter.services.kinozal_search_service._fetch_page")
    def test_4k_empty_and_hd_empty_returns_nothing(self, fetch_mock):
        fetch_mock.side_effect = [[], []]

        result = search_releases("Not Found", "2026", "4k")

        self.assertEqual(result.items, [])
        self.assertEqual(fetch_mock.call_count, 2)

    @patch("moviefilter.services.kinozal_search_service._fetch_page")
    def test_hd_searches_only_hd(self, fetch_mock):
        fetch_mock.return_value = []

        search_releases("Some Movie", "2024", "hd")

        self.assertEqual(fetch_mock.call_count, 1)
        self.assertEqual(fetch_mock.call_args[0][1].v, 3)
        self.assertEqual(fetch_mock.call_args[0][1].d, "2024")


SEARCH_HTML = """
<table>
  <tr class="bg">
    <td class="nam"><a href="/details.php?id=777">Сердце зверя / Heart of the Beast / 2026 / ПМ / 4K / WEB-DL (2160p)</a></td>
    <td class="s">0.0 GB</td>
    <td class="s">14.29 GB</td>
    <td class="sl_s">5</td>
    <td class="sl_p">2</td>
    <td class="s">17.11.2026</td>
  </tr>
  <tr class="bg">
    <td class="nam"><a href="/details.php?id=778">Сердце зверя / 2026 / РУ, СТ / BDRip (1080p)</a></td>
    <td class="s">0.0 GB</td>
    <td class="s">9.83 GB</td>
    <td class="sl_s">12</td>
    <td class="sl_p">4</td>
    <td class="s">18.11.2026</td>
  </tr>
</table>
"""


class ParseSearchRowsTests(TestCase):
    def test_parse_search_rows_extracts_fields_and_header_parts(self):
        from moviefilter.services.kinozal_search_service import parse_search_rows

        response = SimpleNamespace(content=SEARCH_HTML.encode("utf-8"))
        preferences = SimpleNamespace(kinozal_domain="kinozal.tv")

        # is_4k задаётся качеством поискового запроса, поэтому парсим один HTML
        # дважды — как 4K-выдачу и как HD-выдачу.
        rows_4k = parse_search_rows(response, 7, preferences)
        rows_hd = parse_search_rows(response, 3, preferences)

        self.assertEqual(len(rows_4k), 2)

        first = rows_4k[0]
        self.assertEqual(first.id, 777)
        self.assertEqual(first.size, "14.29 GB")
        self.assertEqual(first.seed, "5")
        self.assertEqual(first.peer, "2")
        self.assertEqual(first.created, "17.11.2026")
        self.assertEqual(first.link, "https://kinozal.tv/details.php?id=777")
        self.assertTrue(first.is_4k)
        self.assertFalse(first.is_sdr)
        self.assertEqual(first.title, "Сердце зверя")
        self.assertEqual(first.original_title, "Heart of the Beast")
        self.assertEqual(first.year, "2026")

        second = rows_hd[1]
        self.assertEqual(second.id, 778)
        self.assertFalse(second.is_4k)
        self.assertEqual(second.title, "Сердце зверя")
        self.assertEqual(second.original_title, "")
        self.assertEqual(second.year, "2026")
