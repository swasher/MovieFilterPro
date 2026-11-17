import json
from unittest.mock import patch

import requests
from django.test import SimpleTestCase

from core.services.ai_client import (
    AI_SESSION_HEADER,
    LocalAIConfig,
    build_ai_headers,
    chat_json_or_none,
    parse_json_object,
    post_chat_completion,
    strip_reasoning,
)


class LocalAIParsingTests(SimpleTestCase):
    def test_strip_reasoning_removes_blocks(self):
        raw = "<think>долго думаю</think>\n{\"score\": 5}"
        self.assertEqual(strip_reasoning(raw), '{"score": 5}')

    def test_parse_plain_json(self):
        self.assertEqual(parse_json_object('{"score": 5}'), {"score": 5})

    def test_parse_fenced_json(self):
        self.assertEqual(parse_json_object('```json\n{"score": 7}\n```'), {"score": 7})

    def test_parse_json_with_surrounding_text(self):
        self.assertEqual(parse_json_object('Вот ответ: {"score": 2} готово'), {"score": 2})

    def test_parse_invalid_json_returns_none(self):
        self.assertIsNone(parse_json_object("не json"))
        self.assertIsNone(parse_json_object(""))


class AiHeadersTests(SimpleTestCase):
    def test_session_header_is_generated(self):
        config = LocalAIConfig(base_url="http://localhost/v1", model="m", api_key="k")

        headers = build_ai_headers(config)

        self.assertTrue(headers[AI_SESSION_HEADER].startswith("ses_"))
        self.assertEqual(headers["Authorization"], "Bearer k")
        self.assertEqual(headers["User-Agent"], "MovieFilterPro/1.0")

    def test_session_header_is_reused_when_given(self):
        config = LocalAIConfig(base_url="http://localhost/v1", model="m", api_key="")

        headers = build_ai_headers(config, session_id="ses_test")

        self.assertEqual(headers[AI_SESSION_HEADER], "ses_test")
        self.assertNotIn("Authorization", headers)


class FakeHttpResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class ChatTransportTests(SimpleTestCase):
    def _config(self):
        return LocalAIConfig(base_url="http://localhost:1234/v1", model="m", api_key="k")

    def test_full_payload_contains_optional_layers(self):
        reply = {"choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}]}
        with patch("requests.post", return_value=FakeHttpResponse(reply)) as post:
            result = post_chat_completion(
                self._config(),
                messages=[{"role": "user", "content": "hi"}],
                temperature=0.1,
                max_tokens=100,
                json_mode=True,
                reasoning_effort="low",
                extra_payload={"chat_template_kwargs": {"enable_thinking": False}},
                session_id="ses_test",
            )

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(headers[AI_SESSION_HEADER], "ses_test")
        self.assertEqual(result.content, '{"ok": true}')
        self.assertEqual(result.finish_reason, "stop")

    def test_no_provider_specific_fields_by_default(self):
        reply = {"choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}]}
        with patch("requests.post", return_value=FakeHttpResponse(reply)) as post:
            post_chat_completion(
                self._config(),
                messages=[{"role": "user", "content": "hi"}],
                temperature=0,
            )

        payload = post.call_args.kwargs["json"]
        self.assertNotIn("chat_template_kwargs", payload)
        self.assertNotIn("reasoning_effort", payload)
        self.assertNotIn("response_format", payload)
        self.assertEqual(post.call_count, 1)

    def test_degrades_optional_layers_on_400(self):
        reply = {"choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}]}
        responses = [FakeHttpResponse({}, status_code=400), FakeHttpResponse(reply)]
        with patch("requests.post", side_effect=responses) as post:
            result = post_chat_completion(
                self._config(),
                messages=[{"role": "user", "content": "hi"}],
                temperature=0,
                json_mode=True,
                reasoning_effort="low",
                extra_payload={"chat_template_kwargs": {"enable_thinking": False}},
            )

        first = post.call_args_list[0].kwargs["json"]
        second = post.call_args_list[1].kwargs["json"]
        self.assertIn("chat_template_kwargs", first)
        self.assertNotIn("chat_template_kwargs", second)
        self.assertIn("response_format", second)
        self.assertEqual(result.content, '{"ok": true}')

    def test_does_not_retry_on_auth_error(self):
        with patch("requests.post", return_value=FakeHttpResponse({}, status_code=401)) as post:
            with self.assertRaises(requests.HTTPError):
                post_chat_completion(
                    self._config(),
                    messages=[{"role": "user", "content": "hi"}],
                    temperature=0,
                )

        self.assertEqual(post.call_count, 1)

    def test_chat_json_or_none_parses_reply(self):
        reply = {"choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}]}
        with patch("requests.post", return_value=FakeHttpResponse(reply)):
            result = chat_json_or_none(
                config=self._config(),
                system_prompt="system",
                user_prompt="user",
                temperature=0,
            )

        self.assertEqual(result, {"ok": True})

    def test_chat_json_or_none_returns_none_on_bad_json(self):
        reply = {"choices": [{"message": {"content": "не json"}, "finish_reason": "stop"}]}
        with patch("requests.post", return_value=FakeHttpResponse(reply)):
            result = chat_json_or_none(
                config=self._config(),
                system_prompt="system",
                user_prompt="user",
                temperature=0,
            )

        self.assertIsNone(result)

    def test_chat_json_or_none_returns_none_on_http_error(self):
        with patch("requests.post", return_value=FakeHttpResponse({}, status_code=500)):
            result = chat_json_or_none(
                config=self._config(),
                system_prompt="system",
                user_prompt="user",
                temperature=0,
            )

        self.assertIsNone(result)
