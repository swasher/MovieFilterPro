import json
from datetime import date, datetime
from pathlib import Path
from django.utils import timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Country
from movie_filter_pro.settings import DEFER, HIGH, LOW, SKIP, WAIT_TRANS
from moviefilter.image_caching import CACHE_STATUS_MISSING, CACHE_STATUS_PENDING, CACHE_STATUS_READY
from moviefilter.models import MovieRSS, UserPreferences
from moviefilter.services.favorite_actor_matcher import FavoriteActorMatcher, normalize_actor_name
from vault.models import FavoritePerson, Person


class KinozalApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="kinozal-user", password="secret")
        self.client.force_login(self.user)
        self.preferences = UserPreferences.objects.create(
            user=self.user,
            last_scan=date(2026, 3, 8),
            kinozal_domain="kinozal.tv",
            cookie_uid="uid123",
            cookie_pass="pass123",
            qbt_url="http://qbittorrent:8080",
            qbt_username="admin",
            qbt_password="qbt-pass",
            torrents_backup_folder=r"C:\temp\backup_torrents",
        )

        self.movie_high = MovieRSS.objects.create(
            priority=HIGH,
            kinozal_id=1001,
            title="Alpha",
            original_title="Alpha Original",
            year="2024",
            tracker_date=date(2026, 3, 8),
            scanned_at=timezone.make_aware(datetime(2026, 3, 9, 12, 0)),
            imdb_rating=7.5,
            kinopoisk_rating=6.5,
            genres="Drama, Sci-Fi",
            countries="USA, UK",
            director="Director One, Director Two",
            actors="Actor One, Actor Two",
            plot="Alpha plot",
            translate="Dubbed",
            poster="https://example.com/poster-a.jpg",
        )
        self.movie_low = MovieRSS.objects.create(
            priority=LOW,
            kinozal_id=1002,
            title="Beta",
            original_title="Beta Original",
            year="2023",
            tracker_date=date(2026, 3, 7),
            scanned_at=timezone.make_aware(datetime(2026, 3, 9, 11, 0)),
            imdb_rating=8.1,
            kinopoisk_rating=7.1,
            genres="Comedy",
            countries="France",
            director="Director Three",
            actors="Actor Three",
            plot="Beta plot",
            translate="Subtitles",
            poster="https://example.com/poster-b.jpg",
        )
        self.movie_defer = MovieRSS.objects.create(
            priority=DEFER,
            kinozal_id=1003,
            title="Gamma",
            original_title="Gamma Original",
            year="2022",
            tracker_date=date(2026, 3, 6),
            scanned_at=timezone.make_aware(datetime(2026, 3, 9, 10, 0)),
            imdb_rating=6.3,
            kinopoisk_rating=5.9,
            genres="Thriller",
            countries="Germany",
            director="Director Four",
            actors="Actor Four",
            plot="Gamma plot",
            translate="Voice over",
            poster="https://example.com/poster-c.jpg",
        )

    def test_movies_endpoint_returns_filtered_page(self):
        response = self.client.get("/api/kinozal/movies", {"priority": "LOW", "q": "Beta"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_count"], 1)
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["title"], "Beta")
        self.assertEqual(payload["items"][0]["priority_key"], "LOW")

    def test_movies_endpoint_sorts_oldest_scanned_first_by_default(self):
        response = self.client.get("/api/kinozal/movies", {"priority": "ALL"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["title"] for item in payload["items"]], ["Gamma", "Beta", "Alpha"])
        self.assertEqual(payload["items"][0]["tracker_date"], "2026-03-06")
        self.assertIn("2026-03-09", payload["items"][0]["scanned_at"])

    def test_movies_endpoint_sorts_newest_scanned_first_when_reversed(self):
        response = self.client.get("/api/kinozal/movies", {"priority": "ALL", "reverse": "true"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["title"] for item in payload["items"]], ["Alpha", "Beta", "Gamma"])

    def test_summary_endpoint_returns_counters(self):
        response = self.client.get("/api/kinozal/summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["last_scan"], "2026-03-08")
        self.assertEqual(payload["high"], 1)
        self.assertEqual(payload["low"], 1)
        self.assertEqual(payload["defer"], 1)
        self.assertEqual(payload["total"], 3)

    def test_movies_endpoint_exposes_only_internal_poster_url(self):
        response = self.client.get("/api/kinozal/movies", {"priority": "HIGH"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["items"][0]["poster_url"],
            f"/api/kinozal/movies/{self.movie_high.pk}/poster",
        )

    @patch("moviefilter.api.get_cached_image_state", return_value=(CACHE_STATUS_PENDING, None))
    def test_poster_endpoint_returns_retryable_response_while_cache_is_pending(self, _cache_state_mock):
        response = self.client.get(f"/api/kinozal/movies/{self.movie_high.pk}/poster")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Retry-After"], "1")

    @patch("moviefilter.api.get_cached_image_state", return_value=(CACHE_STATUS_MISSING, None))
    def test_poster_endpoint_redirects_to_placeholder_when_source_is_missing(self, _cache_state_mock):
        response = self.client.get(f"/api/kinozal/movies/{self.movie_high.pk}/poster")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/static/img/poster-placeholder.svg")
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_poster_endpoint_serves_ready_cached_file(self):
        cached_file = Path(self._testMethodName + ".jpg")
        cached_file.write_bytes(b"poster-data")
        self.addCleanup(cached_file.unlink)

        with patch(
            "moviefilter.api.get_cached_image_state",
            return_value=(CACHE_STATUS_READY, cached_file),
        ):
            response = self.client.get(f"/api/kinozal/movies/{self.movie_high.pk}/poster")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"poster-data")

    @patch("moviefilter.api.remove_cached_image")
    def test_hide_action_updates_priority(self, remove_cached_image_mock):
        response = self.client.post(f"/api/kinozal/movies/{self.movie_high.pk}/hide")

        self.assertEqual(response.status_code, 200)
        self.movie_high.refresh_from_db()
        self.assertEqual(self.movie_high.priority, SKIP)
        remove_cached_image_mock.assert_called_once_with(self.movie_high.pk)

    @patch("moviefilter.api.KinozalDownloadImportService.enqueue_hide_action")
    @patch("moviefilter.api.remove_cached_image")
    def test_delete_action_updates_priority_without_vault_import(
        self,
        remove_cached_image_mock,
        enqueue_hide_action_mock,
    ):
        response = self.client.post(f"/api/kinozal/movies/{self.movie_high.pk}/delete")

        self.assertEqual(response.status_code, 200)
        self.movie_high.refresh_from_db()
        self.assertEqual(self.movie_high.priority, SKIP)
        remove_cached_image_mock.assert_called_once_with(self.movie_high.pk)
        enqueue_hide_action_mock.assert_not_called()

    @patch("moviefilter.api.KinozalDownloadImportService.enqueue_will_watch_action")
    @patch("moviefilter.api.remove_cached_image")
    def test_vault_will_watch_action_updates_priority_and_queues_vault_import(
        self,
        remove_cached_image_mock,
        enqueue_will_watch_action_mock,
    ):
        response = self.client.post(f"/api/kinozal/movies/{self.movie_high.pk}/vault-will-watch")

        self.assertEqual(response.status_code, 200)
        self.movie_high.refresh_from_db()
        self.assertEqual(self.movie_high.priority, SKIP)
        remove_cached_image_mock.assert_called_once_with(self.movie_high.pk)
        enqueue_will_watch_action_mock.assert_called_once_with(
            movie_rss_id=self.movie_high.pk,
            user=self.user,
        )

    @patch("moviefilter.api.remove_cached_image")
    def test_wait_trans_action_updates_priority(self, remove_cached_image_mock):
        response = self.client.post(f"/api/kinozal/movies/{self.movie_low.pk}/wait-trans")

        self.assertEqual(response.status_code, 200)
        self.movie_low.refresh_from_db()
        self.assertEqual(self.movie_low.priority, WAIT_TRANS)
        remove_cached_image_mock.assert_called_once_with(self.movie_low.pk)

    @patch("moviefilter.api.torrent_service.validate_ready")
    @patch("moviefilter.api.torrent_service.add_torrent_from_kinozal")
    @patch("moviefilter.api.fetch_torrent_file")
    def test_download_torrent_adds_to_qbt_and_returns_archive_path(
        self,
        fetch_torrent_file_mock,
        add_torrent_mock,
        validate_ready_mock,
    ):
        from moviefilter.services.torrent_download_service import TorrentFile
        from qbittorrent.services.torrent_service import TorrentAddResult

        fetch_torrent_file_mock.return_value = TorrentFile(
            torrent_id=1001,
            filename="[kinozal.tv]id1001.torrent",
            content=b"d4:info0:e",
        )
        torrent = SimpleNamespace(
            id=42,
            info_hash="a" * 40,
            torrent_file=f"{'a' * 40}.torrent",
            movie_id=None,
        )
        add_torrent_mock.return_value = TorrentAddResult(
            torrent=torrent,
            created=True,
            archive_saved=True,
        )

        response = self.client.post("/api/kinozal/torrents/1001/download")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["info_hash"], "a" * 40)
        self.assertEqual(payload["archive_path"], f"{'a' * 40}.torrent")
        self.assertIn("Torrent добавлен в qBittorrent", payload["message"])
        fetch_torrent_file_mock.assert_called_once()
        add_torrent_mock.assert_called_once()
        _, kwargs = add_torrent_mock.call_args
        self.assertEqual(kwargs["torrent_id"], 1001)
        self.assertEqual(kwargs["source_url"], "https://kinozal.tv/details.php?id=1001")

    @patch("moviefilter.api.torrent_service.validate_ready")
    @patch("moviefilter.services.torrent_download_service.KinozalClient")
    def test_download_torrent_returns_structured_error_when_kinozal_returns_html(
        self,
        kinozal_client_mock,
        validate_ready_mock,
    ):
        fake_response = SimpleNamespace(
            headers={"Content-Type": "text/html"},
            content="oops".encode("windows-1251"),
            status_code=200,
        )
        kinozal_client_mock.return_value.download_torrent.return_value = fake_response

        response = self.client.post("/api/kinozal/torrents/1001/download")

        self.assertEqual(response.status_code, 502)
        payload = response.json()
        self.assertEqual(payload["detail"]["code"], "invalid_torrent_response")

    @patch("moviefilter.api.KinozalDownloadImportService.enqueue_successful_download")
    @patch("moviefilter.api.torrent_service.add_torrent_from_kinozal")
    @patch("moviefilter.api.fetch_torrent_file")
    @patch("moviefilter.api.torrent_service.validate_ready")
    def test_download_torrent_triggers_vault_import_when_movie_id_provided(
        self,
        validate_ready_mock,
        fetch_torrent_file_mock,
        add_torrent_mock,
        enqueue_service_mock,
    ):
        from moviefilter.services.torrent_download_service import TorrentFile
        from qbittorrent.services.torrent_service import TorrentAddResult

        fetch_torrent_file_mock.return_value = TorrentFile(
            torrent_id=1001,
            filename="[kinozal.tv]id1001.torrent",
            content=b"d4:info0:e",
        )
        torrent = SimpleNamespace(
            id=42,
            info_hash="a" * 40,
            torrent_file=f"{'a' * 40}.torrent",
            movie_id=None,
        )
        add_torrent_mock.return_value = TorrentAddResult(
            torrent=torrent,
            created=True,
            archive_saved=True,
        )
        enqueue_service_mock.return_value = SimpleNamespace(
            status="queued",
            message="Torrent добавлен. Импорт в Vault поставлен в очередь",
            operation_id=uuid4(),
        )

        response = self.client.post(
            "/api/kinozal/torrents/1001/download",
            data=json.dumps({"movie_id": self.movie_high.pk}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        enqueue_service_mock.assert_called_once()
        _, kwargs = enqueue_service_mock.call_args
        self.assertEqual(kwargs["movie_rss_id"], self.movie_high.pk)
        self.assertEqual(kwargs["torrent_id"], 1001)
        self.assertEqual(kwargs["user"], self.user)
        self.assertEqual(kwargs["torrent_file"], f"{'a' * 40}.torrent")
        self.assertEqual(kwargs["qbt_torrent_id"], 42)

    def test_requires_authentication(self):
        self.client.logout()

        response = self.client.get("/api/kinozal/movies")

        self.assertEqual(response.status_code, 401)


class FavoriteActorMatcherTests(TestCase):
    def test_normalize_actor_name_cleans_variants(self):
        self.assertEqual(normalize_actor_name("Дайан Лэйн"), "дайан лэйн")
        self.assertEqual(normalize_actor_name("Семён Фурман"), "семен фурман")
        self.assertEqual(normalize_actor_name("Роберт Дауни-мл."), "роберт дауни мл")
        self.assertEqual(normalize_actor_name("Дж. Депп (дубляж)"), "депп")

    def test_fuzzy_match_handles_typos_in_russian_names(self):
        matcher = FavoriteActorMatcher(["Дайан Лейн", "Скарлет Йохансон"])

        self.assertIn("Дайан Лэйн", matcher.favorite_actors(["Брэд Питт", "Дайан Лэйн", "Роберт Дауни мл."]))
        self.assertIn("Скарлетт Йоханссон", matcher.favorite_actors(["Скарлетт Йоханссон"]))
        self.assertNotIn("Брэд Питт", matcher.favorite_actors(["Брэд Питт", "Том Хэнкс"]))

    def test_fuzzy_match_handles_word_order_and_none(self):
        matcher = FavoriteActorMatcher(["Дауни-младший Роберт"])

        self.assertEqual(matcher.favorite_actors(["Роберт Дауни мл."]), ["Роберт Дауни мл."])
        self.assertEqual(matcher.favorite_actors(["Том Хэнкс"]), [])

    def test_exact_match_uses_original_spelling(self):
        matcher = FavoriteActorMatcher(["Дайан Лейн"])

        self.assertEqual(matcher.favorite_actors(["Дайан Лейн", "Брэд Питт"]), ["Дайан Лейн"])

    def test_low_cutoff_does_not_match_unrelated_names(self):
        matcher = FavoriteActorMatcher(["Том Хэнкс", "Мэрил Стрип"], score_cutoff=80.0)

        actors = ["Дайан Лэйн", "Кайл Чендлер", "Скай Янг", "Сельда Кая"]
        self.assertEqual(matcher.favorite_actors(actors), [])


class KinozalApiFavoriteActorsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="fav-actor-user", password="secret")
        self.client.force_login(self.user)
        UserPreferences.objects.create(user=self.user, kinozal_domain="kinozal.tv")

        self.country = Country.objects.create(name="USA", code="US")
        self.person = Person.objects.create(
            tmdb_id="100",
            imdb_id="nm100",
            name="Дайан Лэйн",
            original_name="Diane Lane",
            country=self.country,
        )
        FavoritePerson.objects.create(user=self.user, person=self.person)

        self.movie = MovieRSS.objects.create(
            priority=HIGH,
            kinozal_id=2001,
            title="Alpha",
            original_title="Alpha Original",
            year="2024",
            tracker_date=date(2026, 3, 8),
            scanned_at=timezone.make_aware(datetime(2026, 3, 9, 12, 0)),
            genres="Drama",
            countries="USA",
            director="Director",
            actors="Дайан Лейн, Брэд Питт",
            plot="Alpha plot",
            translate="Dubbed",
            poster="https://example.com/poster-a.jpg",
        )

    def test_movies_endpoint_marks_favorite_actors(self):
        response = self.client.get("/api/kinozal/movies", {"priority": "ALL"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        item = payload["items"][0]
        self.assertEqual(item["favorite_actors"], ["Дайан Лейн"])
        self.assertEqual(item["favorite_directors"], [])
