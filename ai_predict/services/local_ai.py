"""
Клиент локальной LLM: OpenAI-совместимый `/chat/completions`.

Настройки берём из Preferences (ai_enabled / ai_base_url / ai_api_key / ai_model).
Никакой привязки к конкретному серверу: Ollama, LM Studio, Lemonade, Unsloth и т.п.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

import requests

from moviefilter.models import UserPreferences

DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_ATTEMPTS = 2
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 700


class LocalAIError(Exception):
    """Локальный AI недоступен или не настроен. Текст показывается пользователю."""


@dataclass(frozen=True)
class LocalAIConfig:
    base_url: str
    model: str
    api_key: str


def get_local_ai_config() -> LocalAIConfig:
    preferences = UserPreferences.get()

    base_url = (getattr(preferences, "ai_base_url", "") or "").strip().rstrip("/")
    model = (getattr(preferences, "ai_model", "") or "").strip()
    api_key = (getattr(preferences, "ai_api_key", "") or "").strip()

    if not getattr(preferences, "ai_enabled", False):
        raise LocalAIError(
            "Локальный AI выключен: включите его в Preferences → Local AI и сохраните настройки."
        )
    if not base_url or not model:
        raise LocalAIError(
            "Не настроен локальный AI: укажите Base URL и Model в Preferences → Local AI."
        )

    return LocalAIConfig(base_url=base_url, model=model, api_key=api_key)


def chat_completions_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


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


def chat_json(
    *,
    config: LocalAIConfig,
    system_prompt: str,
    user_prompt: str,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    attempts: int = DEFAULT_ATTEMPTS,
) -> tuple[dict[str, Any], str]:
    """
    Отправляет промпт и возвращает (разобранный JSON, сырой текст ответа).

    Бросает LocalAIError, если модель так и не вернула валидный JSON.
    """
    url = chat_completions_url(config.base_url)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    payload: dict[str, Any] = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        # Qwen3 и родственные модели: просим не тратить токены на reasoning.
        "chat_template_kwargs": {"enable_thinking": False},
    }

    last_error = "пустой ответ"
    for attempt in range(1, attempts + 1):
        try:
            data = _post(url, headers, payload, timeout)
        except requests.RequestException as exc:
            last_error = f"сеть: {exc}"
            if attempt < attempts:
                time.sleep(2 * attempt)
            continue

        content = _extract_message_content(data)
        parsed = parse_json_object(content)
        if parsed is not None:
            return parsed, content

        last_error = f"не JSON: {_clip(content, 160) or 'пусто'}"
        if attempt < attempts:
            time.sleep(1)

    raise LocalAIError(f"Локальная модель не дала корректный JSON ({last_error}).")


def _post(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if response.status_code == 400 and "chat_template_kwargs" in payload:
        # Сервер может не знать про chat_template_kwargs — повторяем без них.
        fallback_payload = dict(payload)
        fallback_payload.pop("chat_template_kwargs", None)
        response = requests.post(url, headers=headers, json=fallback_payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise requests.RequestException("сервер вернул не объект JSON")
    return data


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
        if isinstance(content, str):
            return content
        reasoning = message.get("reasoning_content")
        if isinstance(reasoning, str):
            return reasoning
    text = first.get("text")
    return text if isinstance(text, str) else ""


def _clip(text: str, limit: int) -> str:
    normalized = " ".join((text or "").split())
    return normalized[:limit]
