from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from bestfilmsof.models import BestfilmsEntry, BestfilmsGenreYear, BestfilmsSync
from vault.models import Movie, UserMovie


class BestfilmsofApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="secret"
        )

    def _entry(self, position, imdb_id, tmdb_id, title, score=10.0):
        return BestfilmsEntry.objects.create(
            year=2010,
            genre="drama",
            imdb_id=imdb_id,
            tmdb_id=tmdb_id,
            position=position,
            score=score,
            title=title,
            comp_imdb=0.8,
            comp_critics=0.2,
            comp_awards=0.0,
            comp_boxoffice=0.0,
            fb_critics=0.4,
            fb_boxoffice=0.3,
        )

    def _mark_synced(self):
        BestfilmsSync.objects.create(
            key="list:2010:drama",
            year=2010,
            genre="drama",
            status=BestfilmsSync.Status.IDLE,
            synced_at=timezone.now(),
            finished_at=timezone.now(),
        )

    def test_requires_auth(self):
        response = self.client.get("/api/bestfilmsof/filters")
        self.assertEqual(response.status_code, 401)

    def test_filters(self):
        self.client.force_login(self.user)
        response = self.client.get("/api/bestfilmsof/filters")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("drama", [item["slug"] for item in payload["genres"]])
        self.assertEqual(payload["year_min"], 1874)
        self.assertGreaterEqual(payload["year_max"], 2026)

    def test_movies_list(self):
        self.client.force_login(self.user)
        self._entry(1, "tt1", 101, "First")
        self._entry(2, "tt2", 102, "Second")
        self._mark_synced()

        response = self.client.get(
            "/api/bestfilmsof/movies?year=2010&genre=drama&limit=10"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["state"], "ready")
        self.assertEqual(payload["total"], 2)
        self.assertEqual(
            [movie["imdb_id"] for movie in payload["movies"]], ["tt1", "tt2"]
        )
        self.assertFalse(payload["is_stale"])

    def test_weighted_list(self):
        self.client.force_login(self.user)
        self._entry(1, "tt1", 101, "First")
        self._entry(2, "tt2", 102, "Second")
        self._mark_synced()

        response = self.client.get(
            "/api/bestfilmsof/movies?year=2010&genre=drama&preset=critics&limit=10"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["preset"], "critics")
        self.assertEqual(
            payload["weights"],
            {"imdb": 20, "critics": 60, "awards": 20, "boxoffice": 0},
        )
        self.assertEqual(len(payload["movies"]), 2)

    def test_genre_summary_includes_user_status(self):
        self.client.force_login(self.user)
        BestfilmsGenreYear.objects.create(
            year=2010,
            genre="drama",
            count=5,
            top_imdb_id="tt1",
            top_tmdb_id=101,
            top_title="Top film",
            top_score=88.0,
        )
        BestfilmsSync.objects.create(
            key="summary:drama",
            genre="drama",
            status=BestfilmsSync.Status.IDLE,
            synced_at=timezone.now(),
            finished_at=timezone.now(),
        )
        movie = Movie.objects.create(
            title="Top film",
            tmdb_id=101,
            tmdb_media_type=Movie.TMDBMediaType.MOVIE,
        )
        UserMovie.objects.create(
            user=self.user,
            movie=movie,
            watch_status=UserMovie.WatchStatus.WATCHED,
            is_favorite=True,
            rating=9,
        )

        response = self.client.get("/api/bestfilmsof/genres/drama")
        self.assertEqual(response.status_code, 200)
        item = response.json()["years"][0]
        self.assertEqual(item["watch_status"], "watched")
        self.assertTrue(item["in_favorites"])
        self.assertEqual(item["rating"], 9)

    def test_unknown_genre_is_rejected(self):
        self.client.force_login(self.user)
        response = self.client.get(
            "/api/bestfilmsof/movies?year=2010&genre=unknown"
        )
        self.assertEqual(response.status_code, 400)

    def test_cold_list_enqueues_sync(self):
        self.client.force_login(self.user)
        with patch("bestfilmsof.tasks.bestfilmsof_sync") as task:
            response = self.client.get(
                "/api/bestfilmsof/movies?year=2010&genre=drama&limit=10"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "queued")
        task.assert_called_once()
        row = BestfilmsSync.objects.get(key="list:2010:drama")
        self.assertEqual(row.status, BestfilmsSync.Status.RUNNING)
        self.assertTrue(row.run_token)

    def test_refresh_marks_running(self):
        self.client.force_login(self.user)
        self._entry(1, "tt1", 101, "First")
        self._mark_synced()
        with patch("bestfilmsof.tasks.bestfilmsof_sync") as task:
            response = self.client.post(
                "/api/bestfilmsof/movies/refresh?year=2010&genre=drama"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "queued")
        task.assert_called_once()

    def _create_user_movie(self, tmdb_id: int, watch_status):
        movie = Movie.objects.create(
            title=f"Vault {tmdb_id}",
            tmdb_id=tmdb_id,
            tmdb_media_type=Movie.TMDBMediaType.MOVIE,
        )
        return UserMovie.objects.create(
            user=self.user,
            movie=movie,
            watch_status=watch_status,
        )

    def test_status_filters_and_counts(self):
        self.client.force_login(self.user)
        self._entry(1, "tt1", 101, "Watched")
        self._entry(2, "tt2", 102, "Planned")
        self._entry(3, "tt3", 103, "Unknown")
        self._mark_synced()
        self._create_user_movie(101, UserMovie.WatchStatus.WATCHED)
        self._create_user_movie(102, UserMovie.WatchStatus.PLAN)

        response = self.client.get(
            "/api/bestfilmsof/movies?year=2010&genre=drama&status_filter=all"
        )
        payload = response.json()
        self.assertEqual(payload["counts"], {"all": 3, "unwatched": 2, "will_watch": 1})
        self.assertEqual(len(payload["movies"]), 3)
        states = {movie["tmdb_id"]: movie["watch_status"] for movie in payload["movies"]}
        self.assertEqual(
            states, {101: "watched", 102: "will_watch", 103: None}
        )

        response = self.client.get(
            "/api/bestfilmsof/movies?year=2010&genre=drama&status_filter=unwatched"
        )
        payload = response.json()
        self.assertEqual(
            [movie["imdb_id"] for movie in payload["movies"]], ["tt2", "tt3"]
        )
        self.assertEqual(payload["counts"]["unwatched"], 2)

        response = self.client.get(
            "/api/bestfilmsof/movies?year=2010&genre=drama&status_filter=will_watch"
        )
        payload = response.json()
        self.assertEqual(
            [movie["imdb_id"] for movie in payload["movies"]], ["tt2"]
        )
        self.assertEqual(payload["movies"][0]["watch_status"], "will_watch")

    def test_unknown_status_filter_is_rejected(self):
        self.client.force_login(self.user)
        response = self.client.get(
            "/api/bestfilmsof/movies?year=2010&genre=drama&status_filter=bad"
        )
        self.assertEqual(response.status_code, 400)
