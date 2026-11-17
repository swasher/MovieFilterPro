from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase

from core.models import AiEndpoint, UserPreferences
from core.services import ai_endpoints
from core.services.ai_endpoints import AiEndpointError
from core.services.ai_models import AiModelsError, fetch_model_ids


class _Response:
    def __init__(self, status_code=200, payload=None, raises=None):
        self.status_code = status_code
        self.ok = status_code < 400
        self._payload = payload
        self._raises = raises

    def json(self):
        if self._raises is not None:
            raise self._raises
        return self._payload


class FetchModelIdsTests(SimpleTestCase):
    BASE_URL = "http://localhost:11434/v1"

    def test_openai_format_sorted(self):
        response = _Response(payload={"data": [{"id": "model-b"}, {"id": "model-a"}]})
        with patch("core.services.ai_models.requests.get", return_value=response) as get:
            models = fetch_model_ids(self.BASE_URL, "")

        self.assertEqual(models, ["model-a", "model-b"])
        self.assertEqual(get.call_args.args[0], f"{self.BASE_URL}/models")

    def test_ollama_tags_after_404(self):
        responses = [
            _Response(status_code=404),
            _Response(payload={"models": [{"name": "qwen2.5:7b"}]}),
        ]
        with patch("core.services.ai_models.requests.get", side_effect=responses) as get:
            models = fetch_model_ids(self.BASE_URL, "")

        self.assertEqual(models, ["qwen2.5:7b"])
        # второй URL — Ollama /api/tags без суффикса /v1
        self.assertEqual(get.call_args_list[1].args[0], "http://localhost:11434/api/tags")

    def test_non_json_raises(self):
        response = _Response(payload=None, raises=ValueError("no json"))
        with patch("core.services.ai_models.requests.get", return_value=response):
            with self.assertRaises(AiModelsError):
                fetch_model_ids(self.BASE_URL, "")

    def test_http_error_raises(self):
        response = _Response(status_code=500, payload={})
        with patch("core.services.ai_models.requests.get", return_value=response):
            with self.assertRaises(AiModelsError):
                fetch_model_ids(self.BASE_URL, "")

    def test_all_empty_raises(self):
        with patch("core.services.ai_models.requests.get", return_value=_Response(payload={})):
            with self.assertRaises(AiModelsError):
                fetch_model_ids(self.BASE_URL, "")

    def test_api_key_in_authorization_header(self):
        response = _Response(payload={"data": [{"id": "m"}]})
        with patch("core.services.ai_models.requests.get", return_value=response) as get:
            fetch_model_ids(self.BASE_URL, "secret-key")

        self.assertEqual(
            get.call_args.kwargs["headers"]["Authorization"], "Bearer secret-key"
        )

    def test_empty_api_key_has_no_authorization(self):
        response = _Response(payload={"data": [{"id": "m"}]})
        with patch("core.services.ai_models.requests.get", return_value=response) as get:
            fetch_model_ids(self.BASE_URL, "")

        self.assertNotIn("Authorization", get.call_args.kwargs["headers"])


class ResolveModelsSourceTests(TestCase):
    def setUp(self):
        self.selected = AiEndpoint.objects.create(
            name="Selected", base_url="http://selected:8000/v1", model="m", api_key="selected-secret"
        )
        self.other = AiEndpoint.objects.create(
            name="Other", base_url="http://other:8000/v1", model="m", api_key="other-secret"
        )
        prefs = UserPreferences.get()
        prefs.ai_endpoint = self.selected
        prefs.save()

    def test_explicit_base_url_does_not_use_selected_key(self):
        base_url, api_key = ai_endpoints.resolve_models_source(
            base_url="http://probe:9000/v1", api_key=None, endpoint_id=None
        )

        self.assertEqual(base_url, "http://probe:9000/v1")
        self.assertEqual(api_key, "")

    def test_explicit_base_url_uses_explicit_key_only(self):
        base_url, api_key = ai_endpoints.resolve_models_source(
            base_url="http://probe:9000/v1", api_key="typed-key", endpoint_id=None
        )

        self.assertEqual((base_url, api_key), ("http://probe:9000/v1", "typed-key"))

    def test_endpoint_id_uses_stored_key(self):
        base_url, api_key = ai_endpoints.resolve_models_source(
            base_url=None, api_key=None, endpoint_id=self.other.id
        )

        self.assertEqual((base_url, api_key), ("http://other:8000/v1", "other-secret"))

    def test_falls_back_to_selected_endpoint(self):
        base_url, api_key = ai_endpoints.resolve_models_source(
            base_url=None, api_key=None, endpoint_id=None
        )

        self.assertEqual((base_url, api_key), ("http://selected:8000/v1", "selected-secret"))

    def test_unknown_endpoint_id_raises(self):
        with self.assertRaises(AiEndpointError):
            ai_endpoints.resolve_models_source(base_url=None, api_key=None, endpoint_id=99999)
