import json
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from movie_filter_pro.settings import DEFER, HIGH, LOW, SKIP, WAIT_TRANS
from moviefilter.models import MovieRSS, UserPreferences


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
            torrents_hotfolder=r"C:\temp\torrents",
        )

        self.movie_high = MovieRSS.objects.create(
            priority=HIGH,
            kinozal_id=1001,
            title="Alpha",
            original_title="Alpha Original",
            year="2024",
            date_added=date(2026, 3, 8),
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
            date_added=date(2026, 3, 7),
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
            date_added=date(2026, 3, 6),
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

    @patch("moviefilter.api.get_cached_image_url", side_effect=lambda poster, *_: poster)
    def test_movies_endpoint_returns_filtered_page(self, _cached_image_mock):
        response = self.client.get("/api/kinozal/movies", {"priority": "LOW", "q": "Beta"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_count"], 1)
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["title"], "Beta")
        self.assertEqual(payload["items"][0]["priority_key"], "LOW")

    @patch("moviefilter.api.get_cached_image_url", side_effect=lambda poster, *_: poster)
    def test_movies_endpoint_sorts_oldest_scan_first_by_default(self, _cached_image_mock):
        response = self.client.get("/api/kinozal/movies", {"priority": "ALL"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["title"] for item in payload["items"]], ["Gamma", "Beta", "Alpha"])

    @patch("moviefilter.api.get_cached_image_url", side_effect=lambda poster, *_: poster)
    def test_movies_endpoint_sorts_newest_scan_first_when_reversed(self, _cached_image_mock):
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

    @patch("moviefilter.api.remove_cached_image")
    def test_hide_action_updates_priority(self, remove_cached_image_mock):
        response = self.client.post(f"/api/kinozal/movies/{self.movie_high.pk}/hide")

        self.assertEqual(response.status_code, 200)
        self.movie_high.refresh_from_db()
        self.assertEqual(self.movie_high.priority, SKIP)
        remove_cached_image_mock.assert_called_once_with(self.movie_high.pk)

    @patch("moviefilter.api.remove_cached_image")
    def test_wait_trans_action_updates_priority(self, remove_cached_image_mock):
        response = self.client.post(f"/api/kinozal/movies/{self.movie_low.pk}/wait-trans")

        self.assertEqual(response.status_code, 200)
        self.movie_low.refresh_from_db()
        self.assertEqual(self.movie_low.priority, WAIT_TRANS)
        remove_cached_image_mock.assert_called_once_with(self.movie_low.pk)

    @patch("moviefilter.services.torrent_download_service.KinozalClient")
    def test_download_torrent_writes_file_to_configured_hotfolder(self, kinozal_client_mock):
        fake_response = SimpleNamespace(
            headers={
                "Content-Type": "application/x-bittorrent",
                "content-disposition": 'attachment; filename="[kinozal.tv]id1001.torrent"',
            },
            content=b"torrent-bytes",
            status_code=200,
        )
        kinozal_client_mock.return_value.download_torrent.return_value = fake_response

        with TemporaryDirectory() as temp_dir:
            self.preferences.torrents_hotfolder = temp_dir
            self.preferences.save()

            response = self.client.post("/api/kinozal/torrents/1001/download")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            saved_path = Path(payload["saved_to"])
            self.assertTrue(saved_path.exists())
            self.assertEqual(saved_path.read_bytes(), b"torrent-bytes")
            self.assertIn("Torrent сохранен", payload["message"])

    @patch("moviefilter.services.torrent_download_service.KinozalClient")
    def test_download_torrent_returns_structured_error_when_kinozal_returns_html(self, kinozal_client_mock):
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

    @patch("moviefilter.api.KinozalDownloadImportService.handle_successful_download")
    @patch("moviefilter.services.torrent_download_service.KinozalClient")
    def test_download_torrent_triggers_vault_import_when_movie_id_provided(
        self,
        kinozal_client_mock,
        import_service_mock,
    ):
        fake_response = SimpleNamespace(
            headers={
                "Content-Type": "application/x-bittorrent",
                "content-disposition": 'attachment; filename="[kinozal.tv]id1001.torrent"',
            },
            content=b"torrent-bytes",
            status_code=200,
        )
        kinozal_client_mock.return_value.download_torrent.return_value = fake_response

        with TemporaryDirectory() as temp_dir:
            self.preferences.torrents_hotfolder = temp_dir
            self.preferences.save()

            response = self.client.post(
                "/api/kinozal/torrents/1001/download",
                data=json.dumps({"movie_id": self.movie_high.pk}),
                content_type="application/json",
            )

            self.assertEqual(response.status_code, 200)
            import_service_mock.assert_called_once()
            _, kwargs = import_service_mock.call_args
            self.assertEqual(kwargs["movie_rss_id"], self.movie_high.pk)
            self.assertEqual(kwargs["torrent_id"], 1001)
            self.assertEqual(kwargs["user"], self.user)
            self.assertTrue(Path(kwargs["saved_to"]).exists())

    def test_requires_authentication(self):
        self.client.logout()

        response = self.client.get("/api/kinozal/movies")

        self.assertEqual(response.status_code, 401)
