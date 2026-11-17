from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from core.models import AiEndpoint, UserPreferences
from core.services import ai_models


class AiModelsApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ai-models-user", password="secret")
        self.client.force_login(self.user)
        self.selected = AiEndpoint.objects.create(
            name="Selected", base_url="http://selected:8000/v1", model="m", api_key="selected-secret"
        )
        prefs = UserPreferences.get()
        prefs.ai_endpoint = self.selected
        prefs.save()

    @patch("core.api.ai_models.fetch_model_ids", return_value=["m1", "m2"])
    def test_explicit_base_url_does_not_use_selected_key(self, fetch_mock):
        response = self.client.get("/api/core/ai-models", {"base_url": "http://probe:9000/v1"})

        self.assertEqual(response.status_code, 200)
        fetch_mock.assert_called_once_with("http://probe:9000/v1", "")
        self.assertEqual(response.json()["models"], ["m1", "m2"])

    @patch("core.api.ai_models.fetch_model_ids", return_value=["m1"])
    def test_explicit_base_url_uses_only_explicit_key(self, fetch_mock):
        response = self.client.get(
            "/api/core/ai-models", {"base_url": "http://probe:9000/v1", "api_key": "typed-key"}
        )

        self.assertEqual(response.status_code, 200)
        fetch_mock.assert_called_once_with("http://probe:9000/v1", "typed-key")

    @patch("core.api.ai_models.fetch_model_ids", return_value=["m1"])
    def test_endpoint_id_uses_stored_key(self, fetch_mock):
        response = self.client.get("/api/core/ai-models", {"endpoint_id": self.selected.id})

        self.assertEqual(response.status_code, 200)
        fetch_mock.assert_called_once_with("http://selected:8000/v1", "selected-secret")

    @patch("core.api.ai_models.fetch_model_ids", return_value=["m1"])
    def test_no_params_uses_selected_endpoint(self, fetch_mock):
        response = self.client.get("/api/core/ai-models")

        self.assertEqual(response.status_code, 200)
        fetch_mock.assert_called_once_with("http://selected:8000/v1", "selected-secret")

    def test_unknown_endpoint_id_returns_400(self):
        response = self.client.get("/api/core/ai-models", {"endpoint_id": 99999})

        self.assertEqual(response.status_code, 400)

    @patch("core.api.ai_models.fetch_model_ids", side_effect=ai_models.AiModelsError("boom"))
    def test_fetch_error_returns_502(self, _fetch_mock):
        response = self.client.get("/api/core/ai-models", {"base_url": "http://probe:9000/v1"})

        self.assertEqual(response.status_code, 502)

    def test_requires_authentication(self):
        self.client.logout()

        response = self.client.get("/api/core/ai-models")

        self.assertEqual(response.status_code, 401)
