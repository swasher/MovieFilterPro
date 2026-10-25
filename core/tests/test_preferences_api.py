from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.test import TestCase

from moviefilter.models import UserPreferences


class PreferencesApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="prefs-user", password="secret")
        self.client.force_login(self.user)
        self.preferences = UserPreferences.objects.create(
            user=self.user,
            last_scan=date(2026, 3, 8),
            scan_from_page=4,
            countries="СССР, Россия",
            genres="Мюзикл",
            max_year=1990,
            min_rating=3.0,
            low_countries="Япония",
            low_genres="Ужасы",
            low_max_year=2000,
            low_min_rating=5.0,
            plex_address="http://plex:32400",
            plex_token="plex-token",
            cookie_pass="pass123",
            cookie_uid="uid123",
            kinozal_domain="kinozal.tv",
            kinozal_mirrors=["kinozal.tv"],
            qbt_url="http://qbittorrent:8080",
            qbt_username="admin",
            qbt_password="qbt-pass",
            torrents_backup_folder=r"C:\temp\backup_torrents",
            ignore_title="camrip",
            tmdb_api_key="tmdb-key",
            omdb_api_key="omdb-key",
            tmdb_v4_read_access_token="tmdb-read-token",
            tmdb_v4_authenticated_access_token="tmdb-auth-token",
        )

    def test_get_preferences_returns_resolved_backup_folder_data(self):
        with TemporaryDirectory() as temp_dir:
            self.preferences.torrents_backup_folder = temp_dir
            self.preferences.save()

            response = self.client.get("/api/core/preferences")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["kinozal_domain"], "kinozal.tv")
            self.assertEqual(payload["resolved_torrents_backup_folder"], str(Path(temp_dir)))
            self.assertTrue(payload["backup_folder_exists"])
            self.assertEqual(payload["qbt_url"], "http://qbittorrent:8080")
            self.assertEqual(payload["qbt_username"], "admin")
            self.assertEqual(payload["qbt_password"], "qbt-pass")
            self.assertEqual(payload["tmdb_v4_authenticated_access_token"], "tmdb-auth-token")
            self.assertEqual(payload["omdb_api_key"], "omdb-key")

    def test_put_preferences_updates_values_and_trims_optional_fields(self):
        response = self.client.put(
            "/api/core/preferences",
            data={
                "last_scan": "2026-03-09",
                "scan_from_page": 9,
                "countries": "Россия, Индия",
                "genres": "Драма",
                "max_year": 1995,
                "min_rating": 4.2,
                "low_countries": "Корея",
                "low_genres": "Триллер",
                "low_max_year": 2005,
                "low_min_rating": 6.1,
                "plex_address": "  http://new-plex:32400  ",
                "plex_token": "  new-plex-token  ",
                "cookie_pass": "  new-pass  ",
                "cookie_uid": "  new-uid  ",
                "kinozal_domain": "  kinozal.guru  ",
                "kinozal_mirrors": ["kinozal.guru"],
                "qbt_url": "  http://new-qbt:8080  ",
                "qbt_username": "  new-admin  ",
                "qbt_password": "new-qbt-pass",
                "torrents_backup_folder": "  C:\\downloads\\backup_torrents  ",
                "ignore_title": "ts, camrip",
                "tmdb_api_key": "  new-tmdb-key  ",
                "omdb_api_key": "  new-omdb-key  ",
                "tmdb_v4_read_access_token": "  new-read-token  ",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.preferences.refresh_from_db()
        self.assertEqual(self.preferences.last_scan.isoformat(), "2026-03-09")
        self.assertEqual(self.preferences.scan_from_page, 9)
        self.assertEqual(self.preferences.kinozal_domain, "kinozal.guru")
        self.assertEqual(self.preferences.qbt_url, "http://new-qbt:8080")
        self.assertEqual(self.preferences.qbt_username, "new-admin")
        self.assertEqual(self.preferences.qbt_password, "new-qbt-pass")
        self.assertEqual(self.preferences.torrents_backup_folder, r"C:\downloads\backup_torrents")
        self.assertEqual(self.preferences.plex_address, "http://new-plex:32400")
        self.assertEqual(self.preferences.tmdb_api_key, "new-tmdb-key")
        self.assertEqual(self.preferences.omdb_api_key, "new-omdb-key")
        self.assertEqual(self.preferences.tmdb_v4_read_access_token, "new-read-token")
        self.assertEqual(self.preferences.tmdb_v4_authenticated_access_token, "tmdb-auth-token")

    def _preferences_payload(self, **overrides) -> dict:
        """Базовый payload для PUT /api/core/preferences."""
        payload = {
            "last_scan": "2026-03-08",
            "scan_from_page": 4,
            "countries": "СССР, Россия",
            "genres": "Мюзикл",
            "max_year": 1990,
            "min_rating": 3.0,
            "low_countries": "Япония",
            "low_genres": "Ужасы",
            "low_max_year": 2000,
            "low_min_rating": 5.0,
            "plex_address": "http://plex:32400",
            "plex_token": "plex-token",
            "cookie_pass": "pass123",
            "cookie_uid": "uid123",
            "kinozal_domain": "kinozal.tv",
            "kinozal_mirrors": ["kinozal.tv"],
            "qbt_url": "http://qbittorrent:8080",
            "qbt_username": "admin",
            "qbt_password": "qbt-pass",
            "torrents_backup_folder": r"C:\temp\backup_torrents",
            "ignore_title": "camrip",
            "tmdb_api_key": "tmdb-key",
            "omdb_api_key": "omdb-key",
            "tmdb_v4_read_access_token": "tmdb-read-token",
        }
        payload.update(overrides)
        return payload

    def test_put_preferences_normalizes_kinozal_mirrors(self):
        response = self.client.put(
            "/api/core/preferences",
            data=self._preferences_payload(
                kinozal_domain="  https://Kinozal.Guru/path  ",
                kinozal_mirrors=[
                    "  kinozal.tv  ",
                    "https://kinozal.guru/",
                    "kinozal.tv",
                    "KINOZAL.ME",
                ],
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.preferences.refresh_from_db()
        self.assertEqual(self.preferences.kinozal_mirrors, ["kinozal.tv", "kinozal.guru", "kinozal.me"])
        # active normalized and forced into the list
        self.assertEqual(self.preferences.kinozal_domain, "kinozal.guru")
        payload = response.json()
        self.assertEqual(payload["kinozal_mirrors"], ["kinozal.tv", "kinozal.guru", "kinozal.me"])

    def test_put_preferences_rejects_invalid_mirror(self):
        response = self.client.put(
            "/api/core/preferences",
            data=self._preferences_payload(
                kinozal_mirrors=["kinozal.tv", "bad domain with spaces", ""],
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.preferences.refresh_from_db()
        # невалидные значения не выкидываются молча, а отвергают весь запрос
        self.assertEqual(self.preferences.kinozal_mirrors, ["kinozal.tv"])

    def test_put_preferences_rejects_active_domain_outside_mirrors(self):
        response = self.client.put(
            "/api/core/preferences",
            data=self._preferences_payload(
                kinozal_domain="kinozal.me",
                kinozal_mirrors=["kinozal.tv"],
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.preferences.refresh_from_db()
        self.assertEqual(self.preferences.kinozal_domain, "kinozal.tv")

    def test_put_preferences_empty_mirrors_clears_active_domain(self):
        response = self.client.put(
            "/api/core/preferences",
            data=self._preferences_payload(kinozal_mirrors=[]),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.preferences.refresh_from_db()
        self.assertEqual(self.preferences.kinozal_mirrors, [])
        # без зеркал активного зеркала не существует
        self.assertIsNone(self.preferences.kinozal_domain)

    def test_preferences_api_requires_authentication(self):
        self.client.logout()

        response = self.client.get("/api/core/preferences")

        self.assertEqual(response.status_code, 401)
