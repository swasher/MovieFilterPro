from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings


class PasswordChangeTests(TestCase):
    url = "/api/auth/password/"
    old_password = "Old-Password-42"
    new_password = "New-Password-77"

    def setUp(self):
        self.user = User.objects.create_user(username="alice", password=self.old_password)
        self.client = Client()
        self.client.force_login(self.user)

    def _change(self, current: str, new: str):
        return self.client.post(
            self.url,
            data={"current_password": current, "new_password": new},
        )

    def test_changes_password_and_keeps_session(self):
        response = self._change(self.old_password, self.new_password)

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))

        session = self.client.get("/api/auth/session/").json()
        self.assertTrue(session["is_authenticated"])

    def test_rejects_wrong_current_password(self):
        response = self._change("wrong-password", self.new_password)

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def test_rejects_same_password(self):
        response = self._change(self.old_password, self.old_password)

        self.assertEqual(response.status_code, 400)

    def test_rejects_missing_fields(self):
        response = self._change("", "")

        self.assertEqual(response.status_code, 400)

    def test_requires_authentication(self):
        self.client.logout()

        response = self._change(self.old_password, self.new_password)

        self.assertEqual(response.status_code, 401)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def test_enforces_password_validators_outside_debug(self):
        response = self._change(self.old_password, "1234")

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    @override_settings(DEBUG=True)
    def test_debug_mode_allows_short_dev_password(self):
        response = self._change(self.old_password, "1234")

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("1234"))

    def test_password_change_rotates_session_auth_hash(self):
        hash_before = self.user.get_session_auth_hash()

        self._change(self.old_password, self.new_password)

        self.user.refresh_from_db()
        self.assertNotEqual(hash_before, self.user.get_session_auth_hash())
