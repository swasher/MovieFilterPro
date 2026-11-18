from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from movie_filter_pro.settings import HIGH
from moviefilter.models import MovieRSS
from qbittorrent.models import Torrent
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
            "tracker_date": date(2026, 3, 9),
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
            torrent_file="/tmp/queued.torrent",
        )

        self.assertEqual(result.status, "queued")
        queue_task_mock.assert_called_once()
        self.assertTrue(
            VaultConnectionEvent.objects.filter(
                operation_id=result.operation_id,
                event_type="torrent_added",
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
        qbt_torrent = Torrent.objects.create(
            info_hash="a" * 40,
            name="Интерстеллар 1080p",
        )

        result = KinozalDownloadImportService.handle_successful_download(
            movie_rss_id=rss_movie.id,
            torrent_id=4001,
            user=self.user,
            torrent_file="/tmp/test.torrent",
            qbt_torrent_id=qbt_torrent.id,
        )

        imported_movie.refresh_from_db()
        qbt_torrent.refresh_from_db()
        self.assertEqual(result.status, "created")
        self.assertEqual(imported_movie.imdb_id, "tt0816692")
        self.assertEqual(imported_movie.kinopoisk_id, 258687)
        self.assertEqual(qbt_torrent.movie, imported_movie)
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

    @patch("vault.tasks.process_kinozal_will_watch_action")
    def test_enqueue_will_watch_action_logs_queue_event(self, queue_task_mock):
        rss_movie = self._create_rss_movie()

        result = KinozalDownloadImportService.enqueue_will_watch_action(
            movie_rss_id=rss_movie.id,
            user=self.user,
        )

        self.assertEqual(result.status, "queued")
        queue_task_mock.assert_called_once()
        self.assertTrue(
            VaultConnectionEvent.objects.filter(
                operation_id=result.operation_id,
                event_type="will_watch_requested",
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
    def test_hide_action_imports_movie_and_sets_wont_watch(self, find_by_imdb_id_mock, import_movie_mock):
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

        result = KinozalDownloadImportService.handle_hide_action(
            movie_rss_id=rss_movie.id,
            user=self.user,
        )

        self.assertEqual(result.status, "created")
        self.assertEqual(
            UserMovie.objects.get(user=self.user, movie=imported_movie).watch_status,
            UserMovie.WatchStatus.SKIP,
        )
        self.assertTrue(
            VaultConnectionEvent.objects.filter(
                operation_id=result.operation_id,
                event_type="wont_watch_applied",
            ).exists()
        )

    @patch("vault.services.kinozal_download_import_service.TMDBMovieImportService.import_movie")
    @patch("vault.services.kinozal_download_import_service.TMDBMovieMatchingService.find_by_imdb_id")
    def test_will_watch_action_imports_movie_and_sets_will_watch(self, find_by_imdb_id_mock, import_movie_mock):
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

        result = KinozalDownloadImportService.handle_will_watch_action(
            movie_rss_id=rss_movie.id,
            user=self.user,
        )

        self.assertEqual(result.status, "created")
        self.assertEqual(
            UserMovie.objects.get(user=self.user, movie=imported_movie).watch_status,
            UserMovie.WatchStatus.PLAN,
        )
        self.assertTrue(
            VaultConnectionEvent.objects.filter(
                operation_id=result.operation_id,
                event_type="will_watch_applied",
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
            torrent_file="/tmp/test-1.torrent",
        )
        second = KinozalDownloadImportService.handle_successful_download(
            movie_rss_id=rss_movie.id,
            torrent_id=4001,
            user=self.user,
            torrent_file="/tmp/test-2.torrent",
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
            torrent_file="/tmp/test-fallback.torrent",
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
            torrent_file="/tmp/test-ambiguous.torrent",
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
            torrent_file="/tmp/test-not-found.torrent",
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


class KinozalDirectDownloadImportServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="direct-vault-user", password="secret")

    @staticmethod
    def _direct_metadata(**overrides):
        payload = {
            "title": "Сердце зверя",
            "original_title": "Heart of the Beast",
            "year": "2026",
            "imdb_id": "tt1234567",
            "kinopoisk_id": 258687,
            "torrent_id": 7001,
            "torrent_file": "/tmp/direct.torrent",
        }
        payload.update(overrides)
        return payload

    @staticmethod
    def _candidate(tmdb_id=777, media_type="movie"):
        return TMDBCandidate(
            tmdb_id=tmdb_id,
            media_type=media_type,
            title="Сердце зверя",
            original_title="Heart of the Beast",
            year=2026,
            score=100,
            score_reasons=("imdb_id_lookup",),
            poster_path="/poster.jpg",
            popularity=99.0,
            vote_average=8.0,
        )

    @patch("vault.tasks.process_kinozal_direct_download_import")
    def test_enqueue_direct_download_import_logs_queue_events(self, queue_task_mock):
        result = KinozalDownloadImportService.enqueue_direct_download_import(
            **self._direct_metadata(),
            user=self.user,
        )

        self.assertEqual(result.status, "queued")
        queue_task_mock.assert_called_once()
        self.assertTrue(
            VaultConnectionEvent.objects.filter(
                operation_id=result.operation_id,
                event_type="direct_download_requested",
            ).exists()
        )
        self.assertTrue(
            VaultConnectionEvent.objects.filter(
                operation_id=result.operation_id,
                event_type="direct_import_queued",
            ).exists()
        )

    @patch("vault.services.kinozal_download_import_service.TMDBMovieImportService.import_movie")
    @patch("vault.services.kinozal_download_import_service.TMDBMovieMatchingService.find_by_imdb_id")
    def test_direct_download_imports_movie_sets_status_and_links_qbt(self, find_by_imdb_id_mock, import_movie_mock):
        candidate = self._candidate()
        find_by_imdb_id_mock.return_value = TMDBMatchingResult(
            status="auto_match",
            selected_candidate=candidate,
            candidates=(candidate,),
            message="TMDB match",
        )
        imported_movie = Movie.objects.create(
            title="Сердце зверя",
            original_title="Heart of the Beast",
            year=2026,
            movie_type=Movie.MovieType.MOVIE,
            status=Movie.Status.RELEASED,
            source=Movie.Source.TMDB,
            tmdb_id=777,
            tmdb_media_type="movie",
        )
        import_movie_mock.return_value = SimpleNamespace(
            status="created",
            message="Фильм добавлен в Vault",
            movie=imported_movie,
        )
        qbt_torrent = Torrent.objects.create(
            info_hash="b" * 40,
            name="Сердце зверя 4K",
        )

        result = KinozalDownloadImportService.handle_direct_download_import(
            **self._direct_metadata(),
            user=self.user,
            qbt_torrent_id=qbt_torrent.id,
        )

        imported_movie.refresh_from_db()
        qbt_torrent.refresh_from_db()
        self.assertEqual(result.status, "created")
        self.assertEqual(imported_movie.imdb_id, "tt1234567")
        self.assertEqual(imported_movie.kinopoisk_id, 258687)
        self.assertEqual(qbt_torrent.movie, imported_movie)
        self.assertEqual(
            UserMovie.objects.get(user=self.user, movie=imported_movie).watch_status,
            UserMovie.WatchStatus.PLAN,
        )
        self.assertTrue(
            VaultConnectionEvent.objects.filter(
                operation_id=result.operation_id,
                event_type="direct_import_started",
            ).exists()
        )
        self.assertTrue(
            VaultConnectionEvent.objects.filter(
                operation_id=result.operation_id,
                event_type="operation_completed",
            ).exists()
        )
        # Записи MovieRSS нет — события не ссылаются на ленту.
        started_event = VaultConnectionEvent.objects.get(
            operation_id=result.operation_id,
            event_type="direct_import_started",
        )
        self.assertIsNone(started_event.movie_rss)
        self.assertEqual(started_event.rss_kinozal_id, 7001)
        self.assertEqual(started_event.imdb_id, "tt1234567")
        self.assertEqual(started_event.kinopoisk_id, 258687)

    def test_direct_download_reuses_existing_movie_and_sets_plan_status(self):
        existing_movie = Movie.objects.create(
            title="Сердце зверя",
            original_title="Heart of the Beast",
            year=2026,
            movie_type=Movie.MovieType.MOVIE,
            status=Movie.Status.RELEASED,
            source=Movie.Source.TMDB,
            tmdb_id=777,
            tmdb_media_type="movie",
            imdb_id="tt1234567",
        )

        result = KinozalDownloadImportService.handle_direct_download_import(
            **self._direct_metadata(),
            user=self.user,
        )

        existing_movie.refresh_from_db()
        self.assertEqual(result.status, "reused")
        self.assertEqual(Movie.objects.count(), 1)
        self.assertEqual(
            UserMovie.objects.get(user=self.user, movie=existing_movie).watch_status,
            UserMovie.WatchStatus.PLAN,
        )
        # kinopoisk_id добит из метаданных раздачи.
        self.assertEqual(existing_movie.kinopoisk_id, 258687)

    def test_direct_download_preserves_existing_user_status(self):
        existing_movie = Movie.objects.create(
            title="Сердце зверя",
            original_title="Heart of the Beast",
            year=2026,
            movie_type=Movie.MovieType.MOVIE,
            status=Movie.Status.RELEASED,
            source=Movie.Source.TMDB,
            tmdb_id=777,
            tmdb_media_type="movie",
            imdb_id="tt1234567",
        )
        UserMovie.objects.create(
            user=self.user,
            movie=existing_movie,
            watch_status=UserMovie.WatchStatus.WATCHED,
        )

        result = KinozalDownloadImportService.handle_direct_download_import(
            **self._direct_metadata(),
            user=self.user,
        )

        self.assertEqual(result.status, "reused")
        self.assertEqual(result.message, "Фильм уже есть в Vault, статус не изменён")
        user_movie = UserMovie.objects.get(user=self.user, movie=existing_movie)
        self.assertEqual(user_movie.watch_status, UserMovie.WatchStatus.WATCHED)

    @patch("vault.services.kinozal_download_import_service.TMDBMovieMatchingService.match_movie")
    def test_direct_download_without_ids_uses_title_year_fallback(self, match_movie_mock):
        """Без imdb/kinopoisk импорт должен использовать fallback-матчинг по названию/году."""
        candidate = self._candidate()
        match_movie_mock.return_value = TMDBMatchingResult(
            status="auto_match",
            selected_candidate=candidate,
            candidates=(candidate,),
            message="TMDB match",
        )
        imported_movie = Movie.objects.create(
            title="Сердце зверя",
            original_title="Heart of the Beast",
            year=2026,
            movie_type=Movie.MovieType.MOVIE,
            status=Movie.Status.RELEASED,
            source=Movie.Source.TMDB,
            tmdb_id=777,
            tmdb_media_type="movie",
        )
        with patch(
            "vault.services.kinozal_download_import_service.TMDBMovieImportService.import_movie",
            return_value=SimpleNamespace(
                status="created",
                message="Фильм добавлен в Vault",
                movie=imported_movie,
            ),
        ):
            result = KinozalDownloadImportService.handle_direct_download_import(
                **self._direct_metadata(imdb_id=None, kinopoisk_id=None),
                user=self.user,
            )

        self.assertEqual(result.status, "created")
        match_movie_mock.assert_called_once()
        probe_movie = match_movie_mock.call_args[0][0]
        self.assertEqual(probe_movie.title, "Сердце зверя")
        self.assertEqual(probe_movie.original_title, "Heart of the Beast")
        self.assertEqual(probe_movie.year, 2026)


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
