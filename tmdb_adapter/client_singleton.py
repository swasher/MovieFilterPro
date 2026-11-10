from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional
from tmdbapis import TMDbAPIs
from threading import Lock
from moviefilter.models import UserPreferences

_tmdb_instance: Optional[TMDbAPIs] = None
_tmdb_config: Optional[dict] = None
_last_key = None
_last_token = None
_tmdb_instance_en: Optional[TMDbAPIs] = None
_last_key_en = None
_last_token_en = None
_lock = Lock()


def get_tmdb_client() -> TMDbAPIs:
    global _tmdb_instance, _tmdb_config, _last_key, _last_token

    pref = UserPreferences.get()
    api_key = pref.tmdb_api_key
    v4_token = pref.tmdb_v4_authenticated_access_token

    with _lock:
        # Пересоздание, если ключи изменились (например, пользователь авторизовался заново)
        if (
                _tmdb_instance is None or
                api_key != _last_key or
                v4_token != _last_token
        ):
            _tmdb_instance = TMDbAPIs(api_key, v4_access_token=v4_token, language="RU")
            _last_key = api_key
            _last_token = v4_token

            # запрашиваем конфигурацию 1 раз
            try:
                _tmdb_config = _tmdb_instance.configuration()
            except Exception:
                _tmdb_config = None

        return _tmdb_instance


def get_tmdb_client_en() -> TMDbAPIs:
    """Клиент с языком EN: английские названия/описания для умного поиска."""
    global _tmdb_instance_en, _last_key_en, _last_token_en

    pref = UserPreferences.get()
    api_key = pref.tmdb_api_key
    v4_token = pref.tmdb_v4_authenticated_access_token

    with _lock:
        if (
                _tmdb_instance_en is None or
                api_key != _last_key_en or
                v4_token != _last_token_en
        ):
            _tmdb_instance_en = TMDbAPIs(api_key, v4_access_token=v4_token, language="EN")
            _last_key_en = api_key
            _last_token_en = v4_token

        return _tmdb_instance_en


def get_tmdb_config() -> Optional[dict]:
    return _tmdb_config


def get_english_title(
    tmdb_id: int,
    media_type: str = "movie",
    tmdb: Optional[TMDbAPIs] = None,
) -> Optional[str]:
    """Возвращает en-US title/name для фильма или сериала.

    Дёргает только базовые детали TMDB (без credits/images), чтобы backfill
    английских названий был дешёвым. Сетевые/API-ошибки наружу не пробрасываются:
    вызывающий код просто получает None и сохраняет прежнее значение.

    `tmdb` позволяет переиспользовать один EN-клиент в цикле backfill.
    """
    if not tmdb_id:
        return None

    normalized_media_type = (media_type or "movie").strip().lower()
    try:
        tmdb = tmdb or get_tmdb_client_en()
        if normalized_media_type == "tv":
            data = tmdb._api.tv_get_details(int(tmdb_id), language="en-US")
            value = data.get("name") if isinstance(data, dict) else None
        else:
            data = tmdb._api.movies_get_details(int(tmdb_id), language="en-US")
            value = data.get("title") if isinstance(data, dict) else None
    except Exception:
        return None

    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text or None


@dataclass(frozen=True, slots=True)
class PersonBasic:
    """Только базовые поля TMDB-персоны, без кредитов, фото и переводов."""

    name: str
    imdb_id: str | None
    birthday: date | None
    deathday: date | None
    place_of_birth: str
    known_for_department: str
    also_known_as: list[str]
    profile_path: str | None
    gender: int | None
    biography: str
    popularity: float | None


def _parse_tmdb_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_person_basic(tmdb: TMDbAPIs, person_id: int) -> Optional[PersonBasic]:
    """
    Лёгкий запрос /person/{id} без append_to_response.

    Не использует tmdb.person(), потому что тот объект лениво догружает
    кредиты, фото и переводы при обращении к части полей.
    """
    data = tmdb._api.people_get_details(
        person_id,
        language=getattr(tmdb, "language", None),
    )
    if not isinstance(data, dict):
        return None

    raw_aliases = data.get("also_known_as")
    aliases = (
        [item for item in raw_aliases if isinstance(item, str)]
        if isinstance(raw_aliases, list)
        else []
    )

    return PersonBasic(
        name=data.get("name") or "",
        imdb_id=data.get("imdb_id") or None,
        birthday=_parse_tmdb_date(data.get("birthday")),
        deathday=_parse_tmdb_date(data.get("deathday")),
        place_of_birth=data.get("place_of_birth") or "",
        known_for_department=data.get("known_for_department") or "",
        also_known_as=aliases,
        profile_path=data.get("profile_path") or None,
        gender=data.get("gender"),
        biography=data.get("biography") or "",
        popularity=_as_float(data.get("popularity")),
    )


@dataclass(frozen=True, slots=True)
class PersonImageBasic:
    file_path: str


def get_person_images(
    tmdb: TMDbAPIs,
    person_id: int,
    limit: int = 8,
) -> list[PersonImageBasic]:
    """Лёгкий запрос /person/{id}/images без append_to_response."""
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 8
    limit = max(1, min(limit, 20))

    data = tmdb._api.people_get_images(person_id)
    if not isinstance(data, dict):
        return []

    profiles = data.get("profiles")
    if not isinstance(profiles, list):
        return []

    result: list[PersonImageBasic] = []
    for item in profiles:
        if not isinstance(item, dict):
            continue

        file_path = item.get("file_path")
        if not isinstance(file_path, str) or not file_path.strip():
            continue

        result.append(PersonImageBasic(file_path=file_path.strip()))
        if len(result) >= limit:
            break

    return result
