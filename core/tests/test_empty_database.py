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
