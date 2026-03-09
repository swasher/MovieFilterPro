import asyncio
from datetime import date
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase

from movie_filter_pro.settings import HIGH
from moviefilter.classes import KinozalMovie
from moviefilter.models import MovieRSS, UserPreferences
from kinozal_scan.parse import kinozal_scan, movie_audit


class KinozalScanPersistenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="scanner-user", password="secret")
        self.preferences = UserPreferences(user=self.user)
        self.preferences.save()

    @patch("kinozal_scan.parse.movie_audit")
    @patch("kinozal_scan.parse.parse_page")
    def test_kinozal_scan_backfills_external_ids_for_existing_movie(
        self,
        parse_page_mock,
        movie_audit_mock,
    ):
        existing_movie = MovieRSS.objects.create(
            priority=HIGH,
            kinozal_id=5001,
            title="Backfill",
            original_title="Backfill Original",
            year="2024",
            date_added=date(2026, 3, 8),
        )
        scanned_movie = KinozalMovie(
            kinozal_id=5001,
            title="Backfill",
            original_title="Backfill Original",
            year="2024",
            date_added=date(2026, 3, 9),
            imdb_id="tt1234567",
            imdb_rating=7.8,
            kinopoisk_id=654321,
            kinopoisk_rating=8.1,
            genres="Drama",
            countries="USA",
            director="Director One",
            actors=["Actor One"],
            plot="Plot",
            translate="Dubbed",
            poster="https://example.com/poster.jpg",
        )
        parse_page_mock.return_value = ([scanned_movie], True)
        movie_audit_mock.return_value = [scanned_movie]

        counter = kinozal_scan(0, date(2026, 3, 1), self.user, asyncio.Event())

        existing_movie.refresh_from_db()
        self.assertEqual(counter, 1)
        self.assertEqual(existing_movie.imdb_id, "tt1234567")
        self.assertEqual(existing_movie.imdb_rating, 7.8)
        self.assertEqual(existing_movie.kinopoisk_id, 654321)
        self.assertEqual(existing_movie.kinopoisk_rating, 8.1)

    @patch("kinozal_scan.parse.get_details")
    def test_movie_audit_skips_movie_that_already_exists_in_rss(self, get_details_mock):
        MovieRSS.objects.create(
            priority=HIGH,
            kinozal_id=7001,
            title="Duplicate",
            original_title="Duplicate Original",
            year="2025",
            date_added=date(2026, 3, 8),
        )
        candidate = KinozalMovie(
            kinozal_id=7001,
            title="Duplicate",
            original_title="Duplicate Original",
            year="2025",
            date_added=date(2026, 3, 9),
        )
        cancel_event = Mock()
        cancel_event.is_set.return_value = False

        result = movie_audit([candidate], self.user, self.preferences, cancel_event)

        self.assertEqual(result, [])
        get_details_mock.assert_not_called()
