from pathlib import PurePath

from django.utils import timezone
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError
from plexapi.server import PlexServer

from core.models import UserPreferences

from plex.models import PlexLinkState, PlexLibraryItem
from plex.services.plex_link_sync_service import PlexLinkSyncService

api = NinjaAPI(title="Plex API", version="1.0", urls_namespace="plex-api")


class MovieOut(Schema):
    title: str
    original_title: str | None
    file_name: str | None
    file_path: str | None
    year: int | None
    guids: list[str]
    # Связка с Vault (по данным кэша PlexLibraryItem)
    vault_movie_id: int | None = None
    vault_movie_title: str | None = None
    vault_movie_slug: str | None = None
    match_method: str | None = None


class PlexLinkStatusOut(Schema):
    configured: bool
    is_syncing: bool
    last_synced_at: str | None = None
    last_attempt_at: str | None = None
    items_total: int = 0
    matched_total: int = 0
    unmatched_total: int = 0
    last_error: str | None = None


class PlexLinkSyncOut(Schema):
    accepted: bool
    already_running: bool


def _require_api_user(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        raise HttpError(401, "Authentication required")
    return user


def _get_plex_server(user) -> PlexServer:
    prefs = UserPreferences.get()
    
    baseurl = prefs.plex_address
    token = prefs.plex_token
    
    if not baseurl or not token:
        raise HttpError(400, "Plex server is not configured in user preferences")
        
    try:
        return PlexServer(baseurl, token)
    except Exception as e:
        raise HttpError(400, f"Plex Server not found at {baseurl}: {str(e)}")


def _datetime_to_iso(value) -> str | None:
    if value is None:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    return value.isoformat()


def _build_link_status() -> PlexLinkStatusOut:
    state = PlexLinkState.get()
    return PlexLinkStatusOut(
        configured=PlexLinkSyncService.is_configured(),
        is_syncing=state.is_syncing,
        last_synced_at=_datetime_to_iso(state.last_synced_at),
        last_attempt_at=_datetime_to_iso(state.last_attempt_at),
        items_total=state.items_total,
        matched_total=state.matched_total,
        unmatched_total=state.unmatched_total,
        last_error=state.last_error or None,
    )


@api.get("/link/status", response=PlexLinkStatusOut)
def get_link_status(request):
    _require_api_user(request)
    return _build_link_status()


@api.post("/link/sync", response=PlexLinkSyncOut)
def sync_link(request):
    """Поставить синхронизацию связи Vault <-> Plex в фоновую очередь."""
    _require_api_user(request)
    if not PlexLinkSyncService.is_configured():
        raise HttpError(400, "Plex server is not configured in user preferences")

    state = PlexLinkState.get()
    if state.is_syncing:
        return PlexLinkSyncOut(accepted=False, already_running=True)

    PlexLinkState.objects.filter(pk=state.pk).update(last_attempt_at=timezone.now())

    from plex.tasks import sync_plex_link

    sync_plex_link()
    return PlexLinkSyncOut(accepted=True, already_running=False)


@api.get("/sections", response=list[str])
def get_sections(request):
    user = _require_api_user(request)
    plexserver = _get_plex_server(user)
    
    try:
        sections_obj_list = plexserver.library.sections()
        sections = [x.title for x in sections_obj_list]
        return sections
    except Exception as e:
        raise HttpError(500, f"Failed to retrieve Plex sections: {str(e)}")


@api.get("/sections/{section_name}/movies", response=list[MovieOut])
def get_movies(request, section_name: str):
    user = _require_api_user(request)
    # Обновляем кэш связи в фоне, чтобы бейджи Vault на странице Plex были актуальны.
    PlexLinkSyncService.ensure_fresh_async()
    plexserver = _get_plex_server(user)
    
    try:
        m = plexserver.library.section(section_name)
    except Exception:
        raise HttpError(404, f"Section '{section_name}' not found")
        
    try:
        movies = m.search()
        result = []
        rating_keys = [str(getattr(mov, 'ratingKey', '') or '') for mov in movies]
        link_rows = (
            PlexLibraryItem.objects
            .filter(rating_key__in=rating_keys, vault_movie__isnull=False)
            .select_related('vault_movie')
        )
        links_by_key = {row.rating_key: row for row in link_rows}

        for mov, rating_key in zip(movies, rating_keys):
            file_path = None
            file_name = None
            media_list = getattr(mov, "media", None) or []
            if media_list:
                for media in media_list:
                    if media.parts:
                        for part in media.parts:
                            if part.file:
                                file_path = part.file
                                file_name = PurePath(part.file).name
                                break
                    if file_path:
                        break
            
            guids = []
            for g in getattr(mov, "guids", []):
                g_str = str(g)
                if g_str.startswith("<Guid:") and g_str.endswith(">"):
                    g_str = g_str[6:-1]
                guids.append(g_str)

            link = links_by_key.get(rating_key)
            result.append(MovieOut(
                title=mov.title or "",
                original_title=getattr(mov, "originalTitle", None),
                file_name=file_name,
                file_path=file_path,
                year=mov.year,
                guids=guids,
                vault_movie_id=link.vault_movie_id if link else None,
                vault_movie_title=link.vault_movie.title if link else None,
                vault_movie_slug=link.vault_movie.slug if link else None,
                match_method=link.match_method if link else None,
            ))
        return result
    except Exception as e:
        raise HttpError(500, f"Failed to retrieve movies from section '{section_name}': {str(e)}")
