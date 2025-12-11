from typing import Optional
from tmdbapis import TMDbAPIs
from tmdbapis.exceptions import Authentication
from threading import Lock
from moviefilter.models import UserPreferences

_tmdb_instance: Optional[TMDbAPIs] = None
_last_key = None
_last_token = None
_lock = Lock()


#def get_tmdb_client(api_key: str, v4_token: str) -> TMDbAPIs:
def get_tmdb_client() -> TMDbAPIs:
    global _tmdb_instance, _last_key, _last_token

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

        return _tmdb_instance
