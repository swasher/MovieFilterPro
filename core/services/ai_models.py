"""
Список моделей с AI-сервера.

Пробуем OpenAI-совместимый `/models` и Ollama-native `/api/tags`.
"""

from __future__ import annotations

import requests

DEFAULT_TIMEOUT_SECONDS = 10


class AiModelsError(Exception):
    """Не удалось получить список моделей. Текст показывается пользователю."""


def _candidate_urls(base_url: str) -> list[str]:
    base = base_url.strip().rstrip("/")
    candidates = [f"{base}/models"]
    if base.endswith("/v1"):
        root = base[: -len("/v1")]
        candidates.append(f"{root}/api/tags")
    else:
        candidates.append(f"{base}/v1/models")
        candidates.append(f"{base}/api/tags")
    # de-duplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def _extract_model_ids(payload: object) -> list[str]:
    """Parse both OpenAI (`data[].id`) and Ollama (`models[].name`) formats."""
    if not isinstance(payload, dict):
        return []
    ids: list[str] = []
    data = payload.get("data")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("id"):
                ids.append(str(item["id"]))
    models = payload.get("models")
    if isinstance(models, list):
        for item in models:
            if isinstance(item, dict):
                name = item.get("name") or item.get("id")
                if name:
                    ids.append(str(name))
    # de-duplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for model_id in ids:
        if model_id not in seen:
            seen.add(model_id)
            unique.append(model_id)
    return unique


def fetch_model_ids(base_url: str, api_key: str) -> list[str]:
    """Возвращает отсортированный список id моделей сервера.

    `api_key` — уже резолвенный ключ (пустая строка — без ключа).
    Бросает AiModelsError с причиной последней неудачи.
    """
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    last_error = "unknown error"
    for url in _candidate_urls(base_url):
        try:
            response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            last_error = f"{url}: {exc}"
            continue
        if response.status_code == 404:
            last_error = f"{url}: HTTP 404"
            continue
        if not response.ok:
            raise AiModelsError(f"AI server error at {url}: HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise AiModelsError(f"AI server at {url} returned non-JSON response")
        model_ids = _extract_model_ids(payload)
        if model_ids:
            return sorted(model_ids)
        last_error = f"{url}: empty model list"
    raise AiModelsError(f"No models found on AI server ({last_error})")
