from unittest.mock import patch

from django.test import TestCase

from bestfilmsof.services import read_service
from bestfilmsof.services.sync_service import SyncService
from bestfilmsof.tests.test_sync import client_factory, page, raw_movie
from vault.models import Movie


class ReadServiceTests(TestCase):
    def _sync(self, pages):
        claimed, row, token = SyncService.claim(2010, "drama", force=True)
        self.assertTrue(claimed)
        with patch(
            "bestfilmsof.services.sync_service._enqueue_russian_backfill"
        ), patch(
            "bestfilmsof.services.sync_service.BestfilmsofClient",
            client_factory(pages),
        ):
            result = SyncService.run_claimed(2010, "drama", token)
        self.assertEqual(result["status"], "ok")

    def test_collection_metadata_has_priority(self):
        self._sync([page([raw_movie("tt1", 101, "English title")])])
        Movie.objects.create(
            title="Русское название",
            title_en="Collection english",
            description="Русское описание",
            tmdb_id=101,
            tmdb_media_type=Movie.TMDBMediaType.MOVIE,
        )

        data = read_service.get_movies(2010, "drama", limit=10)
        movie = data["movies"][0]
        self.assertEqual(movie["title"], "Collection english")
        self.assertEqual(movie["title_ru"], "Русское название")
        self.assertEqual(movie["overview_ru"], "Русское описание")
        self.assertTrue(movie["in_collection"])
        self.assertTrue(movie["collection_slug"])

    def test_cache_is_fallback_when_not_in_collection(self):
        self._sync([page([raw_movie("tt1", 101, "English title")])])
        data = read_service.get_movies(2010, "drama", limit=10)
        movie = data["movies"][0]
        self.assertEqual(movie["title"], "English title")
        self.assertEqual(movie["overview"], "English title overview")
        self.assertFalse(movie["in_collection"])

    def test_weighted_rerank(self):
        self._sync(
            [
                page(
                    [
                        raw_movie(
                            "tt1",
                            101,
                            "IMDb strong",
                            position_components={
                                "imdb": 0.9,
                                "critics": 0.1,
                                "awards": 0.0,
                                "boxoffice": 0.0,
                            },
                        ),
                        raw_movie(
                            "tt2",
                            102,
                            "Critics strong",
                            position_components={
                                "imdb": 0.5,
                                "critics": 0.9,
                                "awards": 0.0,
                                "boxoffice": 0.0,
                            },
                        ),
                    ]
                )
            ]
        )
        data = read_service.get_movies_weighted(
            2010,
            "drama",
            {"imdb": 100, "critics": 0, "awards": 0, "boxoffice": 0},
            limit=10,
        )
        self.assertEqual(
            [movie["imdb_id"] for movie in data["movies"]], ["tt1", "tt2"]
        )
        self.assertEqual(data["movies"][0]["position"], 1)

        data = read_service.get_movies_weighted(
            2010,
            "drama",
            {"imdb": 0, "critics": 100, "awards": 0, "boxoffice": 0},
            limit=10,
        )
        self.assertEqual(
            [movie["imdb_id"] for movie in data["movies"]], ["tt2", "tt1"]
        )

    def test_genre_summary_joins_collection(self):
        summary = {
            "genre": "drama",
            "years": [
                {
                    "year": 2010,
                    "count": 10,
                    "movie": raw_movie("tt1", 101, "Top film"),
                }
            ],
        }
        claimed, row, token = SyncService.claim(None, "drama", force=True)
        self.assertTrue(claimed)
        with patch(
            "bestfilmsof.services.sync_service._enqueue_russian_backfill"
        ), patch(
            "bestfilmsof.services.sync_service.BestfilmsofClient",
            client_factory([], summary),
        ):
            SyncService.run_claimed(None, "drama", token)

        Movie.objects.create(
            title="Топ по-русски",
            tmdb_id=101,
            tmdb_media_type=Movie.TMDBMediaType.MOVIE,
        )
        data = read_service.get_genre_summary("drama")
        item = data["years"][0]
        self.assertEqual(item["top_title_ru"], "Топ по-русски")
        self.assertTrue(item["in_collection"])
