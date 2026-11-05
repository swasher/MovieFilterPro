from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from moviefilter.models import UserPreferences


class EmptyDatabaseTests(TestCase):
    """Поведение приложения на базе без пользователей (пустой prod)."""

    def test_session_reports_no_users(self):
        response = self.client.get("/api/auth/session/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["is_authenticated"])
        self.assertFalse(payload["users_exist"])

    def test_session_reports_existing_users(self):
        User.objects.create_user(username="existing-user", password="secret")

        response = self.client.get("/api/auth/session/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["users_exist"])

    def test_user_preferences_get_works_without_users(self):
        preferences = UserPreferences.get()

        self.assertEqual(preferences.pk, 1)
        self.assertIsNone(preferences.user_id)

        # Повторный вызов не должен падать и не должен создавать вторую запись.
        self.assertEqual(UserPreferences.get().pk, 1)

    def test_background_tasks_do_not_run_without_users(self):
        from kinozal_scan.tasks import kinozal_scheduled_scan_tick
        from vault.tasks import tmdb_sync_watchdog

        # close_old_connections в тестовой транзакции закрыл бы соединение с БД.
        with (
            patch("kinozal_scan.tasks.close_old_connections"),
            patch("vault.tasks.close_old_connections"),
        ):
            self.assertIsNone(kinozal_scheduled_scan_tick.call_local())
            self.assertFalse(tmdb_sync_watchdog.call_local())

        self.assertFalse(UserPreferences.objects.exists())
