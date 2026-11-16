"""
Клиент AI: OpenAI-совместимый `/chat/completions`.

Шаблоны подключений живут в `core.AiEndpoint`, активный выбран в
`UserPreferences.ai_endpoint`. Никакой привязки к конкретному серверу:
Ollama, LM Studio, Lemonade, Unsloth, Groq и т.п.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

import requests

from core.models import AiEndpoint
from moviefilter.models import UserPreferences

DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_ATTEMPTS = 2
DEFAULT_TEMPERATURE = 0.2
# JSON-ответ короткий, но reasoning-модели (Qwen3, DeepSeek, Beam и т.п.)
# тратят сотни токенов на размышления до него.
DEFAULT_MAX_TOKENS = 2048
MAX_TOKENS_CEILING = 8192
# Просим минимальный reasoning: задача — короткий JSON, а не рассуждение.
DEFAULT_REASONING_EFFORT = "low"
# На эти статусы имеет смысл повторить запрос без необязательных полей.
RETRYABLE_STATUS_CODES = frozenset({400, 422})

# OpenCode Go требует стабильный ID сессии на каждый диалог (routing + prompt cache).
# Для остальных OpenAI-совместимых серверов лишний заголовок безвреден.
AI_SESSION_HEADER = "x-opencode-session"
AI_USER_AGENT = "MovieFilterPro/1.0"


class LocalAIError(Exception):
    """AI недоступен или не настроен. Текст показывается пользователю."""


@dataclass(frozen=True)
class LocalAIConfig:
    base_url: str
    model: str
    api_key: str
    endpoint_id: int | None = None


def get_ai_config(endpoint_id: int | None = None) -> LocalAIConfig:
    """
    Конфиг активного AI (или явно указанного endpoint).

    `endpoint_id` — точка расширения: отдельные фичи смогут перебивать
    активный endpoint своим выбором.
    """
    preferences = UserPreferences.get()

    if not getattr(preferences, "ai_enabled", False):
        raise LocalAIError(
            "AI выключен: включите его в Preferences → AI и сохраните настройки."
        )

    if endpoint_id is not None:
        endpoint = AiEndpoint.objects.filter(pk=endpoint_id).first()
        if endpoint is None:
            raise LocalAIError("Выбранный AI endpoint не найден.")
    else:
        endpoint = preferences.ai_endpoint
        if endpoint is None:
            raise LocalAIError(
                "Не выбран AI endpoint: добавьте его в Preferences → AI."
            )

    base_url = (endpoint.base_url or "").strip().rstrip("/")
    model = (endpoint.model or "").strip()
    api_key = (endpoint.api_key or "").strip()

    if not base_url or not model:
        raise LocalAIError(
            "Не настроен AI endpoint: укажите Base URL и Model в Preferences → AI."
        )

    return LocalAIConfig(
        base_url=base_url,
        model=model,
        api_key=api_key,
        endpoint_id=endpoint.pk,
    )


def try_get_ai_config(endpoint_id: int | None = None) -> LocalAIConfig | None:
    """Конфиг активного AI или None, если AI выключен/не настроен. Без исключений."""
    try:
        return get_ai_config(endpoint_id)
    except LocalAIError:
        return None
    except Exception:  # noqa: BLE001 — Preferences/БД могут быть ещё не готовы
        return None


def chat_completions_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def new_ai_session_id() -> str:
    """Стабильный на один диалог ID для `x-opencode-session`."""
    return f"ses_{uuid.uuid4().hex}"


def build_ai_headers(config: LocalAIConfig, *, session_id: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": AI_USER_AGENT,
        AI_SESSION_HEADER: session_id or new_ai_session_id(),
    }
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    return headers


def strip_reasoning(text: str) -> str:
    """Убирает блоки рассуждений моделей с «thinking»."""
    cleaned = re.sub(r"<think\b[^>]*>.*?</think\s*>", "", text, flags=re.S | re.I)
    cleaned = re.sub(r"</?think\b[^>]*>", "", cleaned, flags=re.I)
    return cleaned.strip()


def parse_json_object(text: str) -> dict[str, Any] | None:
    """Достаёт первый JSON-объект из ответа модели (снимает ```-обёртки)."""
    cleaned = strip_reasoning(text)
    if not cleaned:
        return None
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        return None

    candidate = cleaned[start : end + 1]
    for variant in (candidate, re.sub(r",\s*([}\]])", r"\1", candidate)):
        try:
            parsed = json.loads(variant)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


@dataclass(frozen=True)
class ChatCompletionResult:
    payload: dict[str, Any]
    content: str
    finish_reason: str


def post_chat_completion(
    config: LocalAIConfig,
    *,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int | None = None,
    json_mode: bool = False,
    reasoning_effort: str | None = None,
    session_id: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> ChatCompletionResult:
    """
    Единственная точка HTTP-запроса к OpenAI-совместимому AI.

    Провайдер-специфичных ветвлений нет: собираем полный payload и на 400/422
    снимаем необязательные слои по одному. Сервер получает максимум того, что
    умеет, а новый провайдер не требует правок в этом модуле.
    """
    url = chat_completions_url(config.base_url)
    headers = build_ai_headers(config, session_id=session_id)

    base: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if max_tokens is not None:
        base["max_tokens"] = max_tokens

    # Порядок = порядок отказа: сначала нестандартные «thinking»-поля, затем JSON-режим.
    optional: list[tuple[str, Any]] = [
        ("chat_template_kwargs", {"enable_thinking": False}),
    ]
    if reasoning_effort:
        optional.append(("reasoning_effort", reasoning_effort))
    if json_mode:
        optional.append(("response_format", {"type": "json_object"}))

    payload = dict(base)
    for key, value in optional:
        payload[key] = value

    response = requests.post(url, headers=headers, json=dict(payload), timeout=timeout)
    for key, _value in optional:
        if response.status_code not in RETRYABLE_STATUS_CODES:
            break
        payload.pop(key, None)
        response = requests.post(url, headers=headers, json=dict(payload), timeout=timeout)

    _raise_for_status_with_body(response)
    data = response.json()
    if not isinstance(data, dict):
        raise requests.RequestException("сервер вернул не объект JSON")
    return ChatCompletionResult(
        payload=data,
        content=_extract_message_content(data),
        finish_reason=_finish_reason(data),
    )


def chat_json(
    *,
    config: LocalAIConfig,
    system_prompt: str,
    user_prompt: str,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    attempts: int = DEFAULT_ATTEMPTS,
    session_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    """
    Отправляет промпт и возвращает (разобранный JSON, сырой текст ответа).

    Бросает LocalAIError, если модель так и не вернула валидный JSON.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    last_error = "пустой ответ"
    current_max_tokens = max_tokens
    for attempt in range(1, attempts + 1):
        try:
            result = post_chat_completion(
                config,
                messages=messages,
                temperature=temperature,
                max_tokens=current_max_tokens,
                json_mode=True,
                reasoning_effort=DEFAULT_REASONING_EFFORT,
                session_id=session_id,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_error = f"сеть: {exc}"
            if attempt < attempts:
                time.sleep(2 * attempt)
            continue

        parsed = parse_json_object(result.content)
        if parsed is not None:
            return parsed, result.content

        last_error = f"не JSON: {_clip(result.content, 200) or 'пусто'}"
        if result.finish_reason:
            last_error += f" | finish_reason={result.finish_reason}"
        if attempt < attempts:
            if result.finish_reason == "length":
                # Ответ обрезан по max_tokens — на следующей попытке даём больше места.
                current_max_tokens = min(current_max_tokens * 2, MAX_TOKENS_CEILING)
            time.sleep(1)

    raise LocalAIError(f"Модель не дала корректный JSON ({last_error}).")



def _raise_for_status_with_body(response) -> None:
    """HTTPError с телом ответа: без него 400 от провайдера невозможно диагностировать."""
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        body = _clip(getattr(response, "text", "") or "", 400)
        if body:
            raise requests.HTTPError(f"{exc} — {body}", response=response) from exc
        raise


def _extract_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        # Некоторые reasoning-модели кладут итог в отдельное поле.
        for key in ("reasoning_content", "reasoning"):
            reasoning = message.get(key)
            if isinstance(reasoning, str) and reasoning.strip():
                return reasoning
    text = first.get("text")
    return text if isinstance(text, str) else ""


def _finish_reason(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        reason = choices[0].get("finish_reason")
        if isinstance(reason, str):
            return reason
    return ""


def _clip(text: str, limit: int) -> str:
    normalized = " ".join((text or "").split())
    return normalized[:limit]
