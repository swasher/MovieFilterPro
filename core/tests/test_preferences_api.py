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
            torrents_hotfolder=r"C:\temp\torrents",
            ignore_title="camrip",
            tmdb_api_key="tmdb-key",
            tmdb_v4_read_access_token="tmdb-read-token",
            tmdb_v4_authenticated_access_token="tmdb-auth-token",
        )

    def test_get_preferences_returns_resolved_hotfolder_data(self):
        with TemporaryDirectory() as temp_dir:
            self.preferences.torrents_hotfolder = temp_dir
            self.preferences.save()

            response = self.client.get("/api/core/preferences")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["kinozal_domain"], "kinozal.tv")
            self.assertEqual(payload["resolved_torrents_hotfolder"], str(Path(temp_dir)))
            self.assertTrue(payload["hotfolder_exists"])
            self.assertEqual(payload["tmdb_v4_authenticated_access_token"], "tmdb-auth-token")

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
                "torrents_hotfolder": "  C:\\downloads\\torrents  ",
                "ignore_title": "ts, camrip",
                "tmdb_api_key": "  new-tmdb-key  ",
                "tmdb_v4_read_access_token": "  new-read-token  ",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.preferences.refresh_from_db()
        self.assertEqual(self.preferences.last_scan.isoformat(), "2026-03-09")
        self.assertEqual(self.preferences.scan_from_page, 9)
        self.assertEqual(self.preferences.kinozal_domain, "kinozal.guru")
        self.assertEqual(self.preferences.torrents_hotfolder, r"C:\downloads\torrents")
        self.assertEqual(self.preferences.plex_address, "http://new-plex:32400")
        self.assertEqual(self.preferences.tmdb_v4_read_access_token, "new-read-token")
        self.assertEqual(self.preferences.tmdb_v4_authenticated_access_token, "tmdb-auth-token")

    def test_preferences_api_requires_authentication(self):
        self.client.logout()

        response = self.client.get("/api/core/preferences")

        self.assertEqual(response.status_code, 401)
