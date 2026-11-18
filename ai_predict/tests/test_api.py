import json
from unittest.mock import patch

import requests
from django.contrib.auth.models import User
from django.test import TestCase

from ai_predict.models import MoviePrediction, TasteProfile
from core.models import AiEndpoint, UserPreferences
from moviefilter.models import MovieRSS
from movie_filter_pro.settings import HIGH
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


class KinozalPredictionApiTests(AiPredictApiTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        configure_ai()
        self.profile = self._create_taste().json()
        self.rss_movie = MovieRSS.objects.create(
            priority=HIGH,
            kinozal_id=123456,
            title="Раздача с трекера",
            original_title="Tracker Release",
            year="2019",
            tracker_date="2019-05-01",
            imdb_rating=6.7,
            kinopoisk_rating=7.1,
            genres="Драма, Триллер",
            countries="США, Канада",
            director="Иван Режиссёров",
            actors="Пётр Актёров, Анна Актрисова",
            plot="Описание раздачи с трекера.",
            translate="Дубляж",
            poster="",
        )

    def _run_kinozal_prediction(self):
        return self.client.post(
            "/api/ai-predict/kinozal/predict",
            data={"rss_movie_id": self.rss_movie.id, "taste_profile_id": self.profile["id"]},
            content_type="application/json",
        )

    def test_predict_builds_card_from_rss_movie(self):
        with patch("requests.post", return_value=FakeResponse(llm_reply('{"score": 7}'))) as post:
            response = self._run_kinozal_prediction()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "done")
        self.assertEqual(payload["score"], 7)
        self.assertEqual(payload["source"], "kinozal")
        self.assertIsNone(payload["movie_id"])
        self.assertEqual(payload["rss_movie_id"], self.rss_movie.id)
        self.assertEqual(payload["movie_title"], "Раздача с трекера")

        user_prompt = post.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertIn("Tracker Release", user_prompt)
        self.assertIn("Драма", user_prompt)
        self.assertIn("Пётр Актёров", user_prompt)

        prediction = MoviePrediction.objects.get(pk=payload["id"])
        self.assertEqual(prediction.input_snapshot["year"], 2019)
        self.assertEqual(prediction.input_snapshot["ratings"]["kinopoisk"], 7.1)
        self.assertEqual(prediction.input_snapshot["ratings"]["imdb"], 6.7)
        self.assertEqual(prediction.input_snapshot["translation"], "Дубляж")

    def test_last_kinozal_prediction_returns_latest(self):
        with patch("requests.post", return_value=FakeResponse(llm_reply('{"score": 4}'))):
            self._run_kinozal_prediction()

        response = self.client.get(
            f"/api/ai-predict/kinozal/predictions/last?rss_movie_id={self.rss_movie.id}"
            f"&taste_profile_id={self.profile['id']}"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["prediction"]
        self.assertIsNotNone(payload)
        self.assertEqual(payload["rss_movie_id"], self.rss_movie.id)
        self.assertEqual(payload["score"], 4)

    def test_last_kinozal_prediction_is_null_when_nothing_ran(self):
        response = self.client.get(
            f"/api/ai-predict/kinozal/predictions/last?rss_movie_id={self.rss_movie.id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["prediction"])

    def test_kinozal_predict_requires_taste_profile(self):
        response = self.client.post(
            "/api/ai-predict/kinozal/predict",
            data={"rss_movie_id": self.rss_movie.id},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("профиль вкусов", response.json()["detail"].lower())

    def test_kinozal_predict_unknown_movie_returns_404(self):
        response = self.client.post(
            "/api/ai-predict/kinozal/predict",
            data={"rss_movie_id": 999999, "taste_profile_id": self.profile["id"]},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
