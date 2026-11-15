"""
Профили вкусов (Taste): CRUD + валидация.

Профиль — это просто текст (markdown/plain), который вводит пользователь.
Здесь нет парсинга: движок предсказания сам решит, как его читать.
"""

from __future__ import annotations

from ai_predict.models import TasteProfile

MAX_NAME_LENGTH = 100
MAX_CONTENT_LENGTH = 200_000


class TasteProfileError(Exception):
    """Ошибка валидации. API превращает её в HTTP 400."""


def _clean_name(raw: str | None) -> str:
    name = (raw or "").strip()
    if not name:
        raise TasteProfileError("Название профиля не может быть пустым.")
    if len(name) > MAX_NAME_LENGTH:
        raise TasteProfileError(f"Название длиннее {MAX_NAME_LENGTH} символов.")
    return name


def _clean_content(raw: str | None) -> str:
    content = (raw or "").replace("\r\n", "\n").replace("\r", "\n")
    if len(content) > MAX_CONTENT_LENGTH:
        raise TasteProfileError(f"Профиль длиннее {MAX_CONTENT_LENGTH} символов.")
    return content


def list_taste_profiles():
    return TasteProfile.objects.all()


def get_taste_profile(profile_id: int) -> TasteProfile | None:
    return TasteProfile.objects.filter(pk=profile_id).first()


def create_taste_profile(*, name: str | None, content: str | None) -> TasteProfile:
    cleaned_name = _clean_name(name)
    if TasteProfile.objects.filter(name=cleaned_name).exists():
        raise TasteProfileError(f"Профиль «{cleaned_name}» уже существует.")
    return TasteProfile.objects.create(
        name=cleaned_name,
        content=_clean_content(content),
    )


def update_taste_profile(
    profile: TasteProfile,
    *,
    name: str | None = None,
    content: str | None = None,
) -> TasteProfile:
    if name is not None:
        cleaned_name = _clean_name(name)
        if TasteProfile.objects.filter(name=cleaned_name).exclude(pk=profile.pk).exists():
            raise TasteProfileError(f"Профиль «{cleaned_name}» уже существует.")
        profile.name = cleaned_name

    if content is not None:
        profile.content = _clean_content(content)

    profile.save()
    return profile


def delete_taste_profile(profile: TasteProfile) -> None:
    """
    Удаляет профиль. Связанные предсказания остаются (taste_profile = NULL),
    чтобы история прогонов не терялась.
    """
    profile.delete()
