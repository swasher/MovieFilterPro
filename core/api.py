from datetime import date

import requests
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from moviefilter.hotfolder import resolve_torrents_hotfolder_path
from moviefilter.models import UserPreferences


api = NinjaAPI(title="Core API", version="1.0", urls_namespace="core-api")

HOTFOLDER_HINT = (
    "На сервере в Docker обычно используется `/torrents_hotfolder`, "
    "а локально на Windows лучше указывать явный путь вроде `\\\\qnap\\TorrentsHotFolder`."
)


class PreferencesOut(Schema):
    last_scan: str | None = None
    scan_from_page: int | None = None
    countries: str
    genres: str
    max_year: int
    min_rating: float
    low_countries: str
    low_genres: str
    low_max_year: int
    low_min_rating: float
    plex_address: str | None = None
    plex_token: str | None = None
    cookie_pass: str | None = None
    cookie_uid: str | None = None
    kinozal_domain: str | None = None
    torrents_hotfolder: str | None = None
    resolved_torrents_hotfolder: str | None = None
    hotfolder_exists: bool = False
    hotfolder_hint: str
    ignore_title: str
    tmdb_api_key: str | None = None
    omdb_api_key: str | None = None
    tmdb_v4_read_access_token: str | None = None
    tmdb_v4_authenticated_access_token: str | None = None
    ai_enabled: bool = False
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_model: str | None = None


class PreferencesUpdateIn(Schema):
    last_scan: date | None = None
    scan_from_page: int | None = None
    countries: str = ""
    genres: str = ""
    max_year: int
    min_rating: float
    low_countries: str = ""
    low_genres: str = ""
    low_max_year: int
    low_min_rating: float
    plex_address: str | None = None
    plex_token: str | None = None
    cookie_pass: str | None = None
    cookie_uid: str | None = None
    kinozal_domain: str | None = None
    torrents_hotfolder: str | None = None
    ignore_title: str = ""
    tmdb_api_key: str | None = None
    omdb_api_key: str | None = None
    tmdb_v4_read_access_token: str | None = None
    ai_enabled: bool = False
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_model: str | None = None


class AiModelsOut(Schema):
    base_url: str
    models: list[str]


def _require_api_user(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        raise HttpError(401, "Authentication required")
    return user


def _normalized_optional_string(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _serialize_preferences(preferences: UserPreferences) -> PreferencesOut:
    configured_hotfolder = _normalized_optional_string(preferences.torrents_hotfolder)
    resolved_hotfolder = None
    hotfolder_exists = False

    if configured_hotfolder:
        try:
            resolved_path = resolve_torrents_hotfolder_path(configured_hotfolder)
            resolved_hotfolder = str(resolved_path)
            hotfolder_exists = resolved_path.exists()
        except ValueError:
            resolved_hotfolder = None
            hotfolder_exists = False

    return PreferencesOut(
        last_scan=preferences.last_scan.isoformat() if preferences.last_scan else None,
        scan_from_page=preferences.scan_from_page,
        countries=preferences.countries or "",
        genres=preferences.genres or "",
        max_year=preferences.max_year,
        min_rating=preferences.min_rating,
        low_countries=preferences.low_countries or "",
        low_genres=preferences.low_genres or "",
        low_max_year=preferences.low_max_year,
        low_min_rating=preferences.low_min_rating,
        plex_address=preferences.plex_address or None,
        plex_token=preferences.plex_token or None,
        cookie_pass=preferences.cookie_pass or None,
        cookie_uid=preferences.cookie_uid or None,
        kinozal_domain=preferences.kinozal_domain or None,
        torrents_hotfolder=preferences.torrents_hotfolder or None,
        resolved_torrents_hotfolder=resolved_hotfolder,
        hotfolder_exists=hotfolder_exists,
        hotfolder_hint=HOTFOLDER_HINT,
        ignore_title=preferences.ignore_title or "",
        tmdb_api_key=preferences.tmdb_api_key or None,
        omdb_api_key=preferences.omdb_api_key or None,
        tmdb_v4_read_access_token=preferences.tmdb_v4_read_access_token or None,
        tmdb_v4_authenticated_access_token=preferences.tmdb_v4_authenticated_access_token or None,
        ai_enabled=preferences.ai_enabled,
        ai_base_url=preferences.ai_base_url or None,
        ai_api_key=preferences.ai_api_key or None,
        ai_model=preferences.ai_model or None,
    )


def _apply_preferences_update(preferences: UserPreferences, payload: PreferencesUpdateIn) -> UserPreferences:
    preferences.last_scan = payload.last_scan
    preferences.scan_from_page = payload.scan_from_page
    preferences.countries = payload.countries
    preferences.genres = payload.genres
    preferences.max_year = payload.max_year
    preferences.min_rating = payload.min_rating
    preferences.low_countries = payload.low_countries
    preferences.low_genres = payload.low_genres
    preferences.low_max_year = payload.low_max_year
    preferences.low_min_rating = payload.low_min_rating
    preferences.plex_address = _normalized_optional_string(payload.plex_address)
    preferences.plex_token = _normalized_optional_string(payload.plex_token)
    preferences.cookie_pass = _normalized_optional_string(payload.cookie_pass)
    preferences.cookie_uid = _normalized_optional_string(payload.cookie_uid)
    preferences.kinozal_domain = _normalized_optional_string(payload.kinozal_domain)
    preferences.torrents_hotfolder = _normalized_optional_string(payload.torrents_hotfolder)
    preferences.ignore_title = payload.ignore_title
    preferences.tmdb_api_key = _normalized_optional_string(payload.tmdb_api_key)
    preferences.omdb_api_key = _normalized_optional_string(payload.omdb_api_key)
    preferences.tmdb_v4_read_access_token = _normalized_optional_string(payload.tmdb_v4_read_access_token)
    preferences.ai_enabled = payload.ai_enabled
    preferences.ai_base_url = _normalized_optional_string(payload.ai_base_url)
    preferences.ai_api_key = _normalized_optional_string(payload.ai_api_key)
    preferences.ai_model = _normalized_optional_string(payload.ai_model)
    preferences.save()
    return preferences


@api.get("/preferences", response=PreferencesOut)
def get_preferences(request):
    _require_api_user(request)
    preferences = UserPreferences.get()
    return _serialize_preferences(preferences)


@api.put("/preferences", response=PreferencesOut)
def update_preferences(request, payload: PreferencesUpdateIn):
    _require_api_user(request)
    preferences = UserPreferences.get()
    updated = _apply_preferences_update(preferences, payload)
    return _serialize_preferences(updated)


# ------------------------------------ #
#          APPLICATION LAYER           #
#   Local AI models listing (OpenAI    #
#   compatible + Ollama native tags)   #
# ------------------------------------ #

def _candidate_ai_models_urls(base_url: str) -> list[str]:
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


@api.get("/ai-models", response=AiModelsOut)
def list_ai_models(request, base_url: str | None = None, api_key: str | None = None):
    """Return model ids available on the local AI server.

    Query params take precedence so the UI can probe an unsaved Base URL
    without saving preferences first. Falls back to saved preferences.
    """
    _require_api_user(request)
    preferences = UserPreferences.get()
    resolved_base_url = (base_url or "").strip() or (preferences.ai_base_url or "").strip()
    if not resolved_base_url:
        raise HttpError(400, "AI base URL is not configured")
    resolved_api_key = (api_key or "").strip() or (preferences.ai_api_key or "").strip() or None

    headers = {"Accept": "application/json"}
    if resolved_api_key:
        headers["Authorization"] = f"Bearer {resolved_api_key}"

    last_error = "unknown error"
    for url in _candidate_ai_models_urls(resolved_base_url):
        try:
            response = requests.get(url, headers=headers, timeout=10)
        except requests.RequestException as exc:
            last_error = f"{url}: {exc}"
            continue
        if response.status_code == 404:
            last_error = f"{url}: HTTP 404"
            continue
        if not response.ok:
            raise HttpError(response.status_code, f"AI server error at {url}: HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise HttpError(502, f"AI server at {url} returned non-JSON response")
        model_ids = _extract_model_ids(payload)
        if model_ids:
            return AiModelsOut(base_url=resolved_base_url.rstrip("/"), models=sorted(model_ids))
        last_error = f"{url}: empty model list"
    raise HttpError(502, f"No models found on AI server ({last_error})")
