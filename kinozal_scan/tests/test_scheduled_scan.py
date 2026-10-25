from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from moviefilter.models import UserPreferences
from kinozal_scan.tasks import DBCancelEvent, _run_scheduled_scan, _should_run


class ScheduledScanGatingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="scheduled-user", password="secret")
        self.preferences = UserPreferences(user=self.user)
        self.preferences.save()

    def test_should_run_false_when_interval_is_none(self):
        self.preferences.scan_interval_minutes = None
        self.assertFalse(_should_run(self.preferences, timezone.now()))

    def test_should_run_false_when_scan_in_progress(self):
        self.preferences.scan_interval_minutes = 60
        self.preferences.scan_in_progress = True
        self.assertFalse(_should_run(self.preferences, timezone.now()))

    def test_should_run_false_when_interval_not_elapsed(self):
        self.preferences.scan_interval_minutes = 60
        self.preferences.last_scheduled_run_at = timezone.now() - timedelta(minutes=10)
        self.assertFalse(_should_run(self.preferences, timezone.now()))

    def test_should_run_true_when_interval_elapsed(self):
        self.preferences.scan_interval_minutes = 60
        self.preferences.last_scheduled_run_at = timezone.now() - timedelta(minutes=61)
        self.assertTrue(_should_run(self.preferences, timezone.now()))

    def test_should_run_true_when_no_previous_run(self):
        self.preferences.scan_interval_minutes = 60
        self.preferences.last_scheduled_run_at = None
        self.assertTrue(_should_run(self.preferences, timezone.now()))


class DBCancelEventTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cancel-user", password="secret")
        self.preferences = UserPreferences(user=self.user)
        self.preferences.save()

    def test_is_set_reads_db_flag(self):
        self.preferences.scan_cancel_requested = False
        self.preferences.save(update_fields=["scan_cancel_requested"])
        self.assertFalse(DBCancelEvent().is_set())

        UserPreferences.objects.filter(pk=1).update(scan_cancel_requested=True)
        self.assertTrue(DBCancelEvent().is_set())


class ScheduledScanRunTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="run-user", password="secret")
        self.preferences = UserPreferences(user=self.user)
        self.preferences.save()

    @patch("kinozal_scan.tasks.send_notification")
    @patch("kinozal_scan.tasks.log")
    @patch("kinozal_scan.tasks.kinozal_scan")
    def test_run_sets_success_status(self, kinozal_scan_mock, log_mock, notify_mock):
        kinozal_scan_mock.return_value = 3

        result = _run_scheduled_scan(self.preferences)

        self.assertEqual(result, {"status": "success"})
        prefs = UserPreferences.get()
        self.assertEqual(prefs.last_scheduled_status, "success")
        self.assertIsNotNone(prefs.last_scheduled_run_at)

    @patch("kinozal_scan.tasks.send_notification")
    @patch("kinozal_scan.tasks.log")
    @patch("kinozal_scan.tasks.kinozal_scan")
    def test_run_sets_error_status_on_exception(self, kinozal_scan_mock, log_mock, notify_mock):
        kinozal_scan_mock.side_effect = RuntimeError("boom")

        result = _run_scheduled_scan(self.preferences)

        self.assertEqual(result, {"status": "error"})
        prefs = UserPreferences.get()
        self.assertEqual(prefs.last_scheduled_status, "error")
