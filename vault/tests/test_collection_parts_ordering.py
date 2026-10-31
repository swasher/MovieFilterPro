from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from vault.api import _build_collection_out, _collection_part_sort_key
from vault.models import Movie


def _part(tmdb_id, title, release_date=None, year=None, order=0, poster_path=None):
    return {
        "tmdb_id": tmdb_id,
        "title": title,
        "original_title": "",
        "poster_path": poster_path,
        "release_date": release_date,
        "year": year,
        "order": order,
    }


class CollectionPartSortKeyTests(SimpleTestCase):
    def test_sorts_by_full_release_date(self):
        parts = [
            _part(2, "Part 2", release_date="2022-08-18", year=2022, order=1),
            _part(1, "Part 1", release_date="2022-04-26", year=2022, order=2),
        ]

        ordered = sorted(parts, key=_collection_part_sort_key)

        self.assertEqual([p["tmdb_id"] for p in ordered], [1, 2])

    def test_undated_parts_go_last_even_without_year(self):
        parts = [
            _part(3, "Announced", release_date=None, year=None, order=0),
            _part(1, "First", release_date="2010-10-12", year=2010, order=1),
            _part(2, "Second", release_date="2012-11-20", year=2012, order=2),
        ]

        ordered = sorted(parts, key=_collection_part_sort_key)

        self.assertEqual([p["tmdb_id"] for p in ordered], [1, 2, 3])

    def test_undated_parts_are_sorted_by_year(self):
        parts = [
            _part(3, "Unknown", release_date=None, year=None, order=0),
            _part(2, "Later", release_date=None, year=2024, order=1),
            _part(1, "Earlier", release_date=None, year=2020, order=2),
        ]

        ordered = sorted(parts, key=_collection_part_sort_key)

        self.assertEqual([p["tmdb_id"] for p in ordered], [1, 2, 3])

    def test_equal_dates_keep_tmdb_order(self):
        parts = [
            _part(2, "Second", release_date="2020-01-01", year=2020, order=1),
            _part(1, "First", release_date="2020-01-01", year=2020, order=0),
        ]

        ordered = sorted(parts, key=_collection_part_sort_key)

        self.assertEqual([p["tmdb_id"] for p in ordered], [1, 2])


class BuildCollectionOutOrderingTests(SimpleTestCase):
    def test_build_collection_out_sorts_parts_chronologically(self):
        collection = SimpleNamespace(
            tmdb_id=1,
            name="Test Collection",
            overview="",
            poster_path=None,
            backdrop_path=None,
            parts_data=[
                _part(100, "Episode 2", release_date="2012-11-20", year=2012, order=0),
                _part(101, "Episode 1", release_date="2010-10-12", year=2010, order=1),
                _part(102, "Announced", release_date=None, year=None, order=2),
            ],
        )
        movie = SimpleNamespace(collection=collection, collection_id=1)

        with patch.object(Movie.objects, "filter") as filter_mock:
            filter_mock.return_value.values.return_value = []
            out = _build_collection_out(movie)

        self.assertIsNotNone(out)
        self.assertEqual([p.tmdb_id for p in out.parts], [101, 100, 102])
