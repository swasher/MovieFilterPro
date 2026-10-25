from datetime import date
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase

from movie_filter_pro.settings import HIGH
from moviefilter.classes import KinozalMovie
from moviefilter.models import MovieRSS, UserPreferences
from kinozal_scan.parse import movie_audit


class KinozalScanPersistenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="scanner-user", password="secret")
        self.preferences = UserPreferences(user=self.user)
        self.preferences.save()

    @patch("kinozal_scan.parse.get_details")
    def test_movie_audit_skips_movie_that_already_exists_in_rss(self, get_details_mock):
        MovieRSS.objects.create(
            priority=HIGH,
            kinozal_id=7001,
            title="Duplicate",
            original_title="Duplicate Original",
            year="2025",
            tracker_date=date(2026, 3, 8),
        )
        candidate = KinozalMovie(
            kinozal_id=7001,
            title="Duplicate",
            original_title="Duplicate Original",
            year="2025",
            tracker_date=date(2026, 3, 9),
        )
        cancel_event = Mock()
        cancel_event.is_set.return_value = False

        result = movie_audit([candidate], self.user, self.preferences, cancel_event)

        self.assertEqual(result, [])
        get_details_mock.assert_not_called()
