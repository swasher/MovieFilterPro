from typing import Optional
from tmdbapis import TMDbAPIs
from tmdbapis.exceptions import Authentication
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