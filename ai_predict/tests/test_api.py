import json
from unittest.mock import patch

import requests
from django.contrib.auth.models import User
from django.test import TestCase

from ai_predict.models import MoviePrediction, TasteProfile
from core.models import AiEndpoint
from moviefilter.models import UserPreferences
from vault.models import Movie


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def llm_reply(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def configure_ai(enabled: bool = True) -> UserPreferences:
    preferences = UserPreferences.get()
    preferences.ai_enabled = enabled
    endpoint = AiEndpoint.objects.first()
    if endpoint is None:
        endpoint = AiEndpoint.objects.create(
            name="Test",
            base_url="http://127.0.0.1:8888/v1",
            model="test-model",
        )
    preferences.ai_endpoint = endpoint
    preferences.save()
    return preferences


class AiPredictApiTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ai-user", password="secret")
        self.movie = Movie.objects.create(
            title="Тестовый фильм",
            year=2020,
            movie_type=Movie.MovieType.MOVIE,
            description="Описание тестового фильма.",
        )

    def _create_taste(self, name="Rita", content="Детективы и триллеры."):
        return self.client.post(
            "/api/ai-predict/tastes",
            data={"name": name, "content": content},
            content_type="application/json",
        )


class TasteProfileApiTests(AiPredictApiTestCase):
    def test_requires_authentication(self):
        response = self.client.get("/api/ai-predict/tastes")

        self.assertEqual(response.status_code, 401)

    def test_crud_flow(self):
        self.client.force_login(self.user)

        create = self._create_taste()
        self.assertEqual(create.status_code, 200)
        profile = create.json()
        self.assertEqual(profile["name"], "Rita")
        self.assertEqual(profile["content"], "Детективы и триллеры.")

        listing = self.client.get("/api/ai-predict/tastes").json()
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]["id"], profile["id"])

        update = self.client.patch(
            f"/api/ai-predict/tastes/{profile['id']}",
            data={"content": "Только триллеры."},
            content_type="application/json",
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.json()["content"], "Только триллеры.")
        self.assertEqual(update.json()["name"], "Rita")

        delete = self.client.delete(f"/api/ai-predict/tastes/{profile['id']}")
        self.assertEqual(delete.status_code, 200)
        self.assertTrue(delete.json()["ok"])
        self.assertFalse(TasteProfile.objects.exists())

    def test_duplicate_name_is_rejected(self):
        self.client.force_login(self.user)
        self._create_taste()

        response = self._create_taste(content="Другое содержимое.")

        self.assertEqual(response.status_code, 400)
        self.assertIn("уже существует", response.json()["detail"])

    def test_empty_name_is_rejected(self):
        self.client.force_login(self.user)

        response = self._create_taste(name="   ")

        self.assertEqual(response.status_code, 400)
        self.assertIn("не может быть пустым", response.json()["detail"])

    def test_update_requires_payload(self):
        self.client.force_login(self.user)
        profile = self._create_taste().json()

        response = self.client.patch(
            f"/api/ai-predict/tastes/{profile['id']}",
            data={},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)


class PromptApiTests(AiPredictApiTestCase):
    def test_requires_authentication(self):
        response = self.client.get("/api/ai-predict/prompt")

        self.assertEqual(response.status_code, 401)

    def test_get_returns_bundled_default(self):
        self.client.force_login(self.user)

        payload = self.client.get("/api/ai-predict/prompt").json()

        self.assertTrue(payload["is_default"])
        self.assertEqual(payload["content"], payload["default_content"])
        self.assertIn("## Формат ответа", payload["content"])

    def test_put_and_reset(self):
        self.client.force_login(self.user)

        saved = self.client.put(
            "/api/ai-predict/prompt",
            data={"content": "Мой системный промпт."},
            content_type="application/json",
        )
        self.assertEqual(saved.status_code, 200)
        self.assertFalse(saved.json()["is_default"])
        self.assertEqual(saved.json()["content"], "Мой системный промпт.")
        self.assertIsNotNone(saved.json()["updated_at"])

        reset = self.client.post("/api/ai-predict/prompt/reset")

        self.assertEqual(reset.status_code, 200)
        self.assertTrue(reset.json()["is_default"])

    def test_empty_prompt_is_rejected(self):
        self.client.force_login(self.user)

        response = self.client.put(
            "/api/ai-predict/prompt",
            data={"content": "   "},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("не может быть пустым", response.json()["detail"])


class PredictionApiTests(AiPredictApiTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        configure_ai()
        self.profile = self._create_taste().json()

    def _run_prediction(self):
        return self.client.post(
            "/api/ai-predict/predict",
            data={"movie_id": self.movie.id, "taste_profile_id": self.profile["id"]},
            content_type="application/json",
        )

    def test_predict_calls_llm_and_stores_result(self):
        verdict = {
            "score": 8,
            "verdict": "maybe",
            "confidence": 0.7,
            "plus": ["Детектив", "Интрига"],
            "minus": ["Затянутость"],
            "unknowns": ["Развязка"],
            "summary": "Хорошо подходит по жанру.",
        }
        with patch("requests.post", return_value=FakeResponse(llm_reply(json.dumps(verdict)))) as post:
            response = self._run_prediction()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "done")
        self.assertEqual(payload["score"], 8)
        # вердикт модели сохраняется как есть, даже если не совпадает с оценкой
        self.assertEqual(payload["verdict"], "maybe")
        self.assertAlmostEqual(payload["confidence"], 0.7)
        self.assertIn("Оценка: 8/10", payload["result_text"])
        self.assertIn("Детектив", payload["result_text"])
        self.assertIn("Плюсы:", payload["result_text"])

        request_payload = post.call_args.kwargs["json"]
        self.assertEqual(request_payload["model"], "test-model")
        request_headers = post.call_args.kwargs["headers"]
        self.assertTrue(request_headers["x-opencode-session"].startswith("ses_"))
        self.assertEqual(request_headers["User-Agent"], "MovieFilterPro/1.0")
        system_prompt = request_payload["messages"][0]["content"]
        user_prompt = request_payload["messages"][1]["content"]
        self.assertIn("Детективы и триллеры.", system_prompt)
        self.assertIn("Тестовый фильм", user_prompt)

        prediction = MoviePrediction.objects.get(pk=payload["id"])
        self.assertEqual(prediction.status, MoviePrediction.Status.DONE)
        self.assertEqual(prediction.score, 8)
        self.assertEqual(prediction.raw_response["summary"], "Хорошо подходит по жанру.")
        self.assertEqual(prediction.input_snapshot["title"], "Тестовый фильм")
        self.assertIsNotNone(prediction.duration_ms)

    def test_predict_parses_fenced_json(self):
        content = '```json\n{"score": 3, "verdict": "skip", "summary": "Не то."}\n```'
        with patch("requests.post", return_value=FakeResponse(llm_reply(content))):
            response = self._run_prediction()

        payload = response.json()
        self.assertEqual(payload["status"], "done")
        self.assertEqual(payload["score"], 3)
        self.assertEqual(payload["verdict"], "skip")

    def test_predict_reads_json_from_reasoning_content(self):
        llm_payload = {
            "choices": [
                {
                    "message": {"content": "", "reasoning_content": '{"score": 7}'},
                    "finish_reason": "stop",
                }
            ]
        }
        with patch("requests.post", return_value=FakeResponse(llm_payload)):
            response = self._run_prediction()

        payload = response.json()
        self.assertEqual(payload["status"], "done")
        self.assertEqual(payload["score"], 7)

    def test_predict_retries_truncated_answer_with_more_tokens(self):
        truncated = {
            "choices": [
                {
                    "message": {"content": "Думаю над фильмом..."},
                    "finish_reason": "length",
                }
            ]
        }
        complete = {
            "choices": [
                {"message": {"content": '{"score": 6}'}, "finish_reason": "stop"}
            ]
        }
        with patch("requests.post", side_effect=[FakeResponse(truncated), FakeResponse(complete)]) as post, \
                patch("core.services.ai_client.time.sleep"):
            response = self._run_prediction()

        payload = response.json()
        self.assertEqual(payload["status"], "done")
        self.assertEqual(payload["score"], 6)
        first_payload = post.call_args_list[0].kwargs["json"]
        second_payload = post.call_args_list[1].kwargs["json"]
        self.assertGreater(second_payload["max_tokens"], first_payload["max_tokens"])
        self.assertEqual(first_payload["reasoning_effort"], "low")
        self.assertEqual(first_payload["response_format"], {"type": "json_object"})

    def test_predict_with_disabled_ai_returns_error(self):
        configure_ai(enabled=False)

        response = self._run_prediction()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertIn("выключен", payload["error"])

    def test_predict_with_invalid_json_returns_error(self):
        with patch("requests.post", return_value=FakeResponse(llm_reply("не json"))), \
                patch("core.services.ai_client.time.sleep"):
            response = self._run_prediction()

        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertIn("корректный JSON", payload["error"])

    def test_predict_requires_taste_profile(self):
        response = self.client.post(
            "/api/ai-predict/predict",
            data={"movie_id": self.movie.id},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("профиль вкусов", response.json()["detail"].lower())

    def test_predict_unknown_movie_returns_404(self):
        response = self.client.post(
            "/api/ai-predict/predict",
            data={"movie_id": 999999, "taste_profile_id": self.profile["id"]},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_predict_unknown_taste_returns_404(self):
        response = self.client.post(
            "/api/ai-predict/predict",
            data={"movie_id": self.movie.id, "taste_profile_id": 999999},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_last_prediction_returns_latest(self):
        with patch("requests.post", return_value=FakeResponse(llm_reply('{"score": 6}'))):
            self._run_prediction()

        response = self.client.get(
            f"/api/ai-predict/predictions/last?movie_id={self.movie.id}&taste_profile_id={self.profile['id']}"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["prediction"]
        self.assertIsNotNone(payload)
        self.assertEqual(payload["movie_id"], self.movie.id)

    def test_last_prediction_is_null_when_nothing_ran(self):
        response = self.client.get(f"/api/ai-predict/predictions/last?movie_id={self.movie.id}")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["prediction"])

    def test_deleting_taste_keeps_prediction_history(self):
        with patch("requests.post", return_value=FakeResponse(llm_reply('{"score": 6}'))):
            self._run_prediction()

        self.client.delete(f"/api/ai-predict/tastes/{self.profile['id']}")

        prediction = MoviePrediction.objects.get()
        self.assertIsNone(prediction.taste_profile_id)


class AiEndpointApiTests(AiPredictApiTestCase):
    def setUp(self):
        super().setUp()
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

    def test_first_endpoint_becomes_active(self):
        created = self._create().json()

        self.assertTrue(created["is_active"])
        listing = self.client.get("/api/core/ai-endpoints").json()
        self.assertEqual(len(listing), 1)
        self.assertTrue(listing[0]["is_active"])
        self.assertTrue(UserPreferences.get().ai_endpoint_id)

    def test_activate_switches_active_endpoint(self):
        first = self._create(name="Local").json()
        second = self._create(name="Groq", base_url="https://api.groq.com/openai/v1", model="llama").json()

        response = self.client.post(f"/api/core/ai-endpoints/{second['id']}/activate")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_active"])
        listing = self.client.get("/api/core/ai-endpoints").json()
        active = [item for item in listing if item["is_active"]]
        self.assertEqual([item["id"] for item in active], [second["id"]])
        self.assertNotEqual(first["id"], second["id"])

    def test_update_and_delete_active_falls_back(self):
        first = self._create(name="Local").json()
        second = self._create(name="Groq", base_url="https://api.groq.com/openai/v1", model="llama").json()
        self.client.post(f"/api/core/ai-endpoints/{second['id']}/activate")

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
