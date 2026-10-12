from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from movie_filter_pro.settings import HIGH
from moviefilter.models import MovieRSS
from vault.models import Movie, UserMovie, VaultConnectionEvent
from vault.services.kinozal_download_import_service import KinozalDownloadImportService
from vault.services.tmdb_movie_matching_service import TMDBCandidate, TMDBMatchingResult


class KinozalDownloadImportServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="vault-user", password="secret")

    def _create_rss_movie(self, **overrides):
        payload = {
            "priority": HIGH,
            "kinozal_id": 1001,
            "title": "Интерстеллар",
            "original_title": "Interstellar",
            "year": "2014",
            "date_added": date(2026, 3, 9),
            "imdb_id": "tt0816692",
            "imdb_rating": 8.7,
            "kinopoisk_id": 258687,
            "kinopoisk_rating": 8.6,
            "genres": "Sci-Fi",
            "countries": "USA",
            "director": "Christopher Nolan",
            "actors": "Matthew McConaughey",
            "plot": "Space travel",
            "translate": "Dubbed",
            "poster": "https://example.com/poster.jpg",
        }
        payload.update(overrides)
        return MovieRSS.objects.create(**payload)

    @staticmethod
    def _candidate(tmdb_id=321, media_type="movie"):
        return TMDBCandidate(
            tmdb_id=tmdb_id,
            media_type=media_type,
            title="Интерстеллар",
            original_title="Interstellar",
            year=2014,
            score=100,
            score_reasons=("imdb_id_lookup",),
            poster_path="/poster.jpg",
            popularity=99.0,
            vote_average=8.7,
        )

    @patch("vault.tasks.process_kinozal_download_import")
    def test_enqueue_successful_download_logs_queue_event(self, queue_task_mock):
        rss_movie = self._create_rss_movie()

        result = KinozalDownloadImportService.enqueue_successful_download(
            movie_rss_id=rss_movie.id,
            torrent_id=4999,
            user=self.user,
            saved_to="/tmp/queued.torrent",
        )

        self.assertEqual(result.status, "queued")
        queue_task_mock.assert_called_once()
        self.assertTrue(
            VaultConnectionEvent.objects.filter(
                operation_id=result.operation_id,
                event_type="download_saved",
            ).exists()
        )
        self.assertTrue(
            VaultConnectionEvent.objects.filter(
                operation_id=result.operation_id,
                event_type="import_queued",
            ).exists()
        )

    @patch("vault.services.kinozal_download_import_service.TMDBMovieImportService.import_movie")
    @patch("vault.services.kinozal_download_import_service.TMDBMovieMatchingService.find_by_imdb_id")
    def test_successful_imdb_flow_imports_movie_sets_status_and_logs_events(self, find_by_imdb_id_mock, import_movie_mock):
        rss_movie = self._create_rss_movie()
        candidate = self._candidate()
        find_by_imdb_id_mock.return_value = TMDBMatchingResult(
            status="auto_match",
            selected_candidate=candidate,
            candidates=(candidate,),
            message="TMDB match",
        )
        imported_movie = Movie.objects.create(
            title="Интерстеллар",
            original_title="Interstellar",
            year=2014,
            movie_type=Movie.MovieType.MOVIE,
            status=Movie.Status.RELEASED,
            source=Movie.Source.TMDB,
            tmdb_id=321,
            tmdb_media_type="movie",
        )
        import_movie_mock.return_value = SimpleNamespace(
            status="created",
            message="Фильм добавлен в Vault",
            movie=imported_movie,
        )

        result = KinozalDownloadImportService.handle_successful_download(
            movie_rss_id=rss_movie.id,
            torrent_id=4001,
            user=self.user,
            saved_to="/tmp/test.torrent",
        )

        imported_movie.refresh_from_db()
        self.assertEqual(result.status, "created")
        self.assertEqual(imported_movie.imdb_id, "tt0816692")
        self.assertEqual(imported_movie.kinopoisk_id, 258687)
        self.assertEqual(
            UserMovie.objects.get(user=self.user, movie=imported_movie).watch_status,
            UserMovie.WatchStatus.PLAN,
        )
        self.assertTrue(
            VaultConnectionEvent.objects.filter(
                operation_id=result.operation_id,
                event_type="operation_completed",
            ).exists()
        )

    @patch("vault.services.kinozal_download_import_service.TMDBMovieMatchingService.find_by_imdb_id")
    def test_repeated_download_reuses_existing_movie_without_duplicates(self, find_by_imdb_id_mock):
        rss_movie = self._create_rss_movie()
        existing_movie = Movie.objects.create(
            title="Интерстеллар",
            original_title="Interstellar",
            year=2014,
            movie_type=Movie.MovieType.MOVIE,
            status=Movie.Status.RELEASED,
            source=Movie.Source.TMDB,
            tmdb_id=321,
            tmdb_media_type="movie",
            imdb_id="tt0816692",
            kinopoisk_id=258687,
        )

        first = KinozalDownloadImportService.handle_successful_download(
            movie_rss_id=rss_movie.id,
            torrent_id=4001,
            user=self.user,
            saved_to="/tmp/test-1.torrent",
        )
        second = KinozalDownloadImportService.handle_successful_download(
            movie_rss_id=rss_movie.id,
            torrent_id=4001,
            user=self.user,
            saved_to="/tmp/test-2.torrent",
        )

        self.assertEqual(Movie.objects.count(), 1)
        self.assertEqual(UserMovie.objects.count(), 1)
        self.assertEqual(first.movie.id, existing_movie.id)
        self.assertEqual(second.movie.id, existing_movie.id)
        find_by_imdb_id_mock.assert_not_called()

    @patch("vault.services.kinozal_download_import_service.TMDBMovieImportService.import_movie")
    @patch("vault.services.kinozal_download_import_service.TMDBMovieMatchingService.match_movie")
    def test_missing_imdb_uses_title_year_fallback(self, match_movie_mock, import_movie_mock):
        rss_movie = self._create_rss_movie(imdb_id=None)
        candidate = self._candidate(tmdb_id=654)
        match_movie_mock.return_value = TMDBMatchingResult(
            status="auto_match",
            selected_candidate=candidate,
            candidates=(candidate,),
            message="Fallback match",
        )
        imported_movie = Movie.objects.create(
            title="Интерстеллар",
            original_title="Interstellar",
            year=2014,
            movie_type=Movie.MovieType.MOVIE,
            status=Movie.Status.RELEASED,
            source=Movie.Source.TMDB,
            tmdb_id=654,
            tmdb_media_type="movie",
        )
        import_movie_mock.return_value = SimpleNamespace(
            status="created",
            message="Фильм добавлен в Vault",
            movie=imported_movie,
        )

        result = KinozalDownloadImportService.handle_successful_download(
            movie_rss_id=rss_movie.id,
            torrent_id=4002,
            user=self.user,
            saved_to="/tmp/test-fallback.torrent",
        )

        self.assertEqual(result.status, "created")
        match_movie_mock.assert_called_once()

    @patch("vault.services.kinozal_download_import_service.TMDBMovieMatchingService.find_by_imdb_id")
    @patch("vault.services.kinozal_download_import_service.TMDBMovieMatchingService.match_movie")
    def test_ambiguous_match_stops_without_creating_movie(self, match_movie_mock, find_by_imdb_id_mock):
        rss_movie = self._create_rss_movie()
        candidate = self._candidate()
        find_by_imdb_id_mock.return_value = TMDBMatchingResult(
            status="needs_user_choice",
            selected_candidate=None,
            candidates=(candidate,),
            message="Несколько кандидатов",
        )
        match_movie_mock.return_value = TMDBMatchingResult(
            status="needs_user_choice",
            selected_candidate=None,
            candidates=(candidate,),
            message="Несколько кандидатов",
        )

        result = KinozalDownloadImportService.handle_successful_download(
            movie_rss_id=rss_movie.id,
            torrent_id=4003,
            user=self.user,
            saved_to="/tmp/test-ambiguous.torrent",
        )

        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(Movie.objects.count(), 0)
        self.assertTrue(
            VaultConnectionEvent.objects.filter(
                operation_id=result.operation_id,
                event_type="tmdb_resolution_stopped",
            ).exists()
        )
        # IMDb ID есть — эвристики по названию не запускаются вовсе.
        match_movie_mock.assert_not_called()

    @patch("vault.services.kinozal_download_import_service.TMDBMovieMatchingService.find_by_imdb_id")
    @patch("vault.services.kinozal_download_import_service.TMDBMovieMatchingService.match_movie")
    def test_not_found_stops_without_creating_movie(self, match_movie_mock, find_by_imdb_id_mock):
        rss_movie = self._create_rss_movie()
        find_by_imdb_id_mock.return_value = TMDBMatchingResult(
            status="not_found",
            selected_candidate=None,
            candidates=tuple(),
            message="Не найдено по IMDb",
        )
        match_movie_mock.return_value = TMDBMatchingResult(
            status="not_found",
            selected_candidate=None,
            candidates=tuple(),
            message="Кандидаты TMDB не найдены",
        )

        result = KinozalDownloadImportService.handle_successful_download(
            movie_rss_id=rss_movie.id,
            torrent_id=4004,
            user=self.user,
            saved_to="/tmp/test-not-found.torrent",
        )

        self.assertEqual(result.status, "not_found")
        self.assertEqual(Movie.objects.count(), 0)
        self.assertTrue(
            VaultConnectionEvent.objects.filter(
                operation_id=result.operation_id,
                event_type="tmdb_resolution_stopped",
            ).exists()
        )
        # IMDb ID есть — эвристики по названию не запускаются вовсе.
        match_movie_mock.assert_not_called()
        event = VaultConnectionEvent.objects.get(
            operation_id=result.operation_id,
            event_type="tmdb_resolution_stopped",
        )
        self.assertEqual(event.message, "Фильм есть на IMDb, но отсутствует на TMDB")


class ConnectionEventsApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="api-user", password="secret")
        self.client.force_login(self.user)

    def test_connection_events_requires_authentication(self):
        self.client.logout()

        response = self.client.get("/api/vault/connection-events")

        self.assertEqual(response.status_code, 401)

    def test_connection_events_returns_event_list(self):
        event = VaultConnectionEvent.objects.create(
            source=VaultConnectionEvent.Source.KINOZAL_DOWNLOAD,
            event_type="download_saved",
            level=VaultConnectionEvent.Level.INFO,
            message="Torrent saved",
            user=self.user,
            rss_kinozal_id=1001,
            torrent_kinozal_id=4001,
        )

        response = self.client.get("/api/vault/connection-events", {"limit": 10})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["items"][0]["id"], event.id)
        self.assertEqual(payload["items"][0]["event_type"], "download_saved")
