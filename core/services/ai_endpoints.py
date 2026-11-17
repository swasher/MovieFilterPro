"""
AI endpoints: CRUD + выбор основного.

Endpoint — это всего лишь «шаблон подключения»: имя, Base URL, модель и
необязательный API-ключ. Никакой провайдерной логики: локальные и облачные
OpenAI-совместимые серверы хранятся одинаково.
"""

from __future__ import annotations

from django.db import transaction

from core.models import AiEndpoint, UserPreferences

MAX_NAME_LENGTH = 100
MAX_BASE_URL_LENGTH = 300
MAX_MODEL_LENGTH = 200
MAX_API_KEY_LENGTH = 300


class AiEndpointError(Exception):
    """Ошибка валидации. API превращает её в HTTP 400."""


def _clean_name(raw: str | None) -> str:
    name = (raw or "").strip()
    if not name:
        raise AiEndpointError("Название endpoint не может быть пустым.")
    if len(name) > MAX_NAME_LENGTH:
        raise AiEndpointError(f"Название длиннее {MAX_NAME_LENGTH} символов.")
    return name


def _clean_base_url(raw: str | None) -> str:
    base_url = (raw or "").strip()
    if not base_url:
        raise AiEndpointError("Base URL не может быть пустым.")
    if not base_url.startswith(("http://", "https://")):
        raise AiEndpointError("Base URL должен начинаться с http:// или https://.")
    base_url = base_url.rstrip("/")
    if len(base_url) > MAX_BASE_URL_LENGTH:
        raise AiEndpointError(f"Base URL длиннее {MAX_BASE_URL_LENGTH} символов.")
    return base_url


def _clean_model(raw: str | None) -> str:
    model = (raw or "").strip()
    if not model:
        raise AiEndpointError("Модель не может быть пустой.")
    if len(model) > MAX_MODEL_LENGTH:
        raise AiEndpointError(f"Название модели длиннее {MAX_MODEL_LENGTH} символов.")
    return model


def _clean_api_key(raw: str | None) -> str:
    api_key = (raw or "").strip()
    if len(api_key) > MAX_API_KEY_LENGTH:
        raise AiEndpointError(f"API-ключ длиннее {MAX_API_KEY_LENGTH} символов.")
    return api_key


def mask_secret(value: str) -> str:
    """Маска секрета для отображения: «••••1234». Короткие — полностью скрыты."""
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "••••"
    return f"••••{value[-4:]}"


def list_endpoints():
    return AiEndpoint.objects.all()


def get_endpoint(endpoint_id: int) -> AiEndpoint | None:
    return AiEndpoint.objects.filter(pk=endpoint_id).first()


def get_selected_endpoint() -> AiEndpoint | None:
    """Выбранный endpoint из Preferences. Не падает, если Preferences ещё нет."""
    try:
        preferences = UserPreferences.get()
    except Exception:  # noqa: BLE001 — Preferences может быть ещё не создан
        return None
    return preferences.ai_endpoint


def resolve_models_source(
    *,
    base_url: str | None,
    api_key: str | None,
    endpoint_id: int | None,
) -> tuple[str, str]:
    """
    Пара (base_url, api_key) для запроса списка моделей.

    Явный base_url никогда не комбинируется с ключом другого endpoint:
    если base_url передан, ключ берётся только из явного api_key (пустой —
    значит без ключа). Иначе используется endpoint по endpoint_id или
    выбранный endpoint со своим сохранённым ключом.
    """
    if base_url is not None and base_url.strip():
        return base_url.strip(), (api_key or "").strip()

    if endpoint_id is not None:
        endpoint = get_endpoint(endpoint_id)
        if endpoint is None:
            raise AiEndpointError("AI endpoint не найден.")
    else:
        endpoint = get_selected_endpoint()
        if endpoint is None:
            raise AiEndpointError("AI endpoint не выбран.")
    return endpoint.base_url.strip(), (endpoint.api_key or "").strip()


def set_selected_endpoint(endpoint: AiEndpoint | None) -> AiEndpoint | None:
    preferences = UserPreferences.get()
    preferences.ai_endpoint = endpoint
    preferences.save(update_fields=["ai_endpoint"])
    return endpoint


def create_endpoint(
    *,
    name: str | None,
    base_url: str | None,
    model: str | None,
    api_key: str | None = "",
    select: bool = False,
    duplicate_of: int | None = None,
) -> AiEndpoint:
    """
    Создаёт endpoint.

    `select` — сразу сделать endpoint выбранным. `duplicate_of` — скопировать
    API-ключ исходного endpoint (явный api_key перекрывает). Создание и выбор
    происходят в одной транзакции: endpoint не останется «осиротевшим»,
    если выбор упадёт.
    """
    cleaned_name = _clean_name(name)
    if AiEndpoint.objects.filter(name=cleaned_name).exists():
        raise AiEndpointError(f"Endpoint «{cleaned_name}» уже существует.")

    copied_api_key = _clean_api_key(api_key)
    if duplicate_of is not None:
        source = get_endpoint(duplicate_of)
        if source is None:
            raise AiEndpointError("Исходный endpoint для дублирования не найден.")
        if not copied_api_key:
            copied_api_key = source.api_key

    with transaction.atomic():
        endpoint = AiEndpoint.objects.create(
            name=cleaned_name,
            base_url=_clean_base_url(base_url),
            model=_clean_model(model),
            api_key=copied_api_key,
        )
        # Первый созданный шаблон сразу становится выбранным, чтобы не было
        # «настроил, но AI всё равно не работает».
        if select or get_selected_endpoint() is None:
            set_selected_endpoint(endpoint)
    return endpoint


def update_endpoint(
    endpoint: AiEndpoint,
    *,
    name: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> AiEndpoint:
    # API-ключ намеренно не участвует в update: он заменяется только через
    # set_endpoint_api_key (отдельный диалог), а на фронт не отдаётся вовсе.
    if name is not None:
        cleaned_name = _clean_name(name)
        if AiEndpoint.objects.filter(name=cleaned_name).exclude(pk=endpoint.pk).exists():
            raise AiEndpointError(f"Endpoint «{cleaned_name}» уже существует.")
        endpoint.name = cleaned_name

    if base_url is not None:
        endpoint.base_url = _clean_base_url(base_url)

    if model is not None:
        endpoint.model = _clean_model(model)

    endpoint.save()
    return endpoint


def set_endpoint_api_key(endpoint: AiEndpoint, api_key: str | None = "") -> AiEndpoint:
    """Заменяет API-ключ endpoint. Пустая строка — ключ снимается."""
    endpoint.api_key = _clean_api_key(api_key)
    endpoint.save(update_fields=["api_key"])
    return endpoint


def delete_endpoint(endpoint: AiEndpoint) -> None:
    """Удаляет endpoint. Если он был выбранным, выбранным становится первый оставшийся."""
    with transaction.atomic():
        selected = get_selected_endpoint()
        was_selected = selected is not None and selected.pk == endpoint.pk
        endpoint.delete()
        if was_selected:
            set_selected_endpoint(AiEndpoint.objects.first())
