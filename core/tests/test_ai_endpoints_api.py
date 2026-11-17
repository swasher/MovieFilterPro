from django.contrib.auth.models import User
from django.test import TestCase

from core.models import AiEndpoint, UserPreferences


class AiEndpointApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="endpoint-user", password="secret")
        self.client.force_login(self.user)

    def _create(self, name="Local", base_url="http://127.0.0.1:11434/v1", model="qwen2.5:7b"):
        return self.client.post(
            "/api/core/ai-endpoints",
            data={"name": name, "base_url": base_url, "model": model},
            content_type="application/json",
        )

    def test_requires_authentication(self):
        self.client.logout()
        response = self.client.get("/api/core/ai-endpoints")

        self.assertEqual(response.status_code, 401)

    def test_first_endpoint_becomes_selected(self):
        created = self._create().json()

        self.assertTrue(created["is_selected"])
        listing = self.client.get("/api/core/ai-endpoints").json()
        self.assertEqual(len(listing), 1)
        self.assertTrue(listing[0]["is_selected"])
        self.assertTrue(UserPreferences.get().ai_endpoint_id)

    def test_select_switches_selected_endpoint(self):
        first = self._create(name="Local").json()
        second = self._create(name="Groq", base_url="https://api.groq.com/openai/v1", model="llama").json()

        response = self.client.post(f"/api/core/ai-endpoints/{second['id']}/select")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_selected"])
        listing = self.client.get("/api/core/ai-endpoints").json()
        selected = [item for item in listing if item["is_selected"]]
        self.assertEqual([item["id"] for item in selected], [second["id"]])
        self.assertNotEqual(first["id"], second["id"])

    def test_create_with_select_true_makes_it_selected(self):
        first = self._create(name="Local").json()

        created = self.client.post(
            "/api/core/ai-endpoints",
            data={
                "name": "Cloud",
                "base_url": "https://api.groq.com/openai/v1",
                "model": "llama",
                "select": True,
            },
            content_type="application/json",
        ).json()

        self.assertTrue(created["is_selected"])
        self.assertEqual(UserPreferences.get().ai_endpoint_id, created["id"])
        self.assertNotEqual(first["id"], created["id"])

    def test_api_key_is_never_returned_in_responses(self):
        created = self.client.post(
            "/api/core/ai-endpoints",
            data={
                "name": "WithKey",
                "base_url": "https://api.groq.com/openai/v1",
                "model": "llama",
                "api_key": "gsk_super-secret-key-1234",
            },
            content_type="application/json",
        ).json()

        self.assertTrue(created["has_api_key"])
        self.assertEqual(created["api_key_masked"], "••••1234")
        self.assertNotIn("api_key", created)
        listing = self.client.get("/api/core/ai-endpoints").json()
        self.assertNotIn("api_key", listing[0])

    def test_patch_does_not_touch_api_key(self):
        created = self.client.post(
            "/api/core/ai-endpoints",
            data={
                "name": "WithKey",
                "base_url": "https://api.groq.com/openai/v1",
                "model": "llama",
                "api_key": "gsk_secret",
            },
            content_type="application/json",
        ).json()

        updated = self.client.patch(
            f"/api/core/ai-endpoints/{created['id']}",
            data={"model": "llama-3.3"},
            content_type="application/json",
        ).json()

        self.assertEqual(updated["model"], "llama-3.3")
        self.assertEqual(AiEndpoint.objects.get(pk=created["id"]).api_key, "gsk_secret")

    def test_put_api_key_sets_and_clears(self):
        created = self._create(name="Local").json()
        endpoint_id = created["id"]

        set_response = self.client.put(
            f"/api/core/ai-endpoints/{endpoint_id}/api-key",
            data={"api_key": "new-key"},
            content_type="application/json",
        )
        self.assertEqual(set_response.status_code, 200)
        self.assertTrue(set_response.json()["has_api_key"])

        clear_response = self.client.put(
            f"/api/core/ai-endpoints/{endpoint_id}/api-key",
            data={"api_key": ""},
            content_type="application/json",
        )
        self.assertEqual(clear_response.status_code, 200)
        self.assertFalse(clear_response.json()["has_api_key"])

    def test_duplicate_copies_api_key_server_side(self):
        created = self.client.post(
            "/api/core/ai-endpoints",
            data={
                "name": "Source",
                "base_url": "https://api.groq.com/openai/v1",
                "model": "llama",
                "api_key": "gsk_source-secret",
            },
            content_type="application/json",
        ).json()

        duplicated = self.client.post(
            "/api/core/ai-endpoints",
            data={
                "name": "Source copy",
                "base_url": "https://api.groq.com/openai/v1",
                "model": "llama",
                "duplicate_of": created["id"],
                "select": True,
            },
            content_type="application/json",
        ).json()

        self.assertTrue(duplicated["has_api_key"])
        self.assertEqual(AiEndpoint.objects.get(pk=duplicated["id"]).api_key, "gsk_source-secret")

    def test_duplicate_of_unknown_endpoint_returns_400(self):
        response = self.client.post(
            "/api/core/ai-endpoints",
            data={
                "name": "Orphan",
                "base_url": "https://api.groq.com/openai/v1",
                "model": "llama",
                "duplicate_of": 99999,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_update_and_delete_selected_falls_back(self):
        first = self._create(name="Local").json()
        second = self._create(name="Groq", base_url="https://api.groq.com/openai/v1", model="llama").json()
        self.client.post(f"/api/core/ai-endpoints/{second['id']}/select")

        updated = self.client.patch(
            f"/api/core/ai-endpoints/{second['id']}",
            data={"model": "llama-3.3-70b-versatile"},
            content_type="application/json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["model"], "llama-3.3-70b-versatile")

        deleted = self.client.delete(f"/api/core/ai-endpoints/{second['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(UserPreferences.get().ai_endpoint_id, first["id"])

    def test_rejects_duplicate_name_and_bad_base_url(self):
        self._create(name="Local")

        duplicate = self._create(name="Local")
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("уже существует", duplicate.json()["detail"])

        bad_url = self._create(name="Broken", base_url="localhost:11434")
        self.assertEqual(bad_url.status_code, 400)
