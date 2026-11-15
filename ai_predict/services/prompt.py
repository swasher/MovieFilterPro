"""
Системный промпт предсказания.

Текст живёт в двух местах:
1. Значение по умолчанию — `ai_predict/prompts/taste_predict.txt` (едет вместе с кодом).
2. Рабочее значение — `PromptTemplate` (singleton в БД), редактируется в Preferences → AI prompt.

Системный промпт описывает только методику оценки и НЕ содержит предпочтений
конкретного человека. Профиль вкусов добавляется в конец автоматически.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_predict.models import PromptTemplate

PROMPT_VERSION = "taste_predict.v2"
DEFAULT_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "taste_predict.txt"
PROFILE_HEADER = "## Профиль человека"
MAX_PROMPT_LENGTH = 100_000


class PromptError(Exception):
    """Промпт недоступен или не прошёл валидацию."""


def get_default_prompt() -> str:
    try:
        return DEFAULT_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise PromptError(f"Не найден шаблон промпта: {DEFAULT_PROMPT_PATH}") from exc


def get_saved_prompt() -> str:
    """Промпт из БД. Пустая строка = используется встроенный."""
    template = PromptTemplate.objects.filter(pk=1).first()
    return (template.content or "").strip() if template else ""


def get_prompt_template() -> str:
    return get_saved_prompt() or get_default_prompt()


def get_prompt_state() -> dict[str, Any]:
    """Состояние для UI: рабочий текст, встроенный текст, флаг «изменён»."""
    saved = get_saved_prompt()
    default = get_default_prompt()
    template = PromptTemplate.objects.filter(pk=1).first()
    return {
        "content": saved or default,
        "default_content": default,
        "is_default": not saved,
        "updated_at": template.updated_at.isoformat() if template else None,
    }


def save_prompt_template(content: str) -> dict[str, Any]:
    cleaned = (content or "").strip()
    if not cleaned:
        raise PromptError("Системный промпт не может быть пустым. Для сброса используйте «Вернуть стандартный».")
    if len(cleaned) > MAX_PROMPT_LENGTH:
        raise PromptError(f"Промпт длиннее {MAX_PROMPT_LENGTH} символов.")

    template, _created = PromptTemplate.objects.get_or_create(pk=1)
    template.content = cleaned
    template.save()
    return get_prompt_state()


def reset_prompt_template() -> dict[str, Any]:
    PromptTemplate.objects.filter(pk=1).delete()
    return get_prompt_state()


def build_system_prompt(profile_content: str) -> str:
    template = get_prompt_template().strip()
    profile = (profile_content or "").strip()
    return f"{template}\n\n{PROFILE_HEADER}\n\n{profile}"


def build_user_prompt(card: dict[str, Any]) -> str:
    return "Оцени фильм по карточке.\n\n" + json.dumps(card, ensure_ascii=False)
