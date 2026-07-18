from pathlib import PurePath
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError
from plexapi.server import PlexServer
from moviefilter.models import UserPreferences

api = NinjaAPI(title="Plex API", version="1.0", urls_namespace="plex-api")


class MovieOut(Schema):
    title: str
    original_title: str | None
    file_name: str | None
    file_path: str | None
    year: int | None
    guids: list[str]


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
    plexserver = _get_plex_server(user)
    
    try:
        m = plexserver.library.section(section_name)
    except Exception:
        raise HttpError(404, f"Section '{section_name}' not found")
        
    try:
        movies = m.search()
        result = []
        for mov in movies:
            file_path = None
            file_name = None
            if mov.media:
                for media in mov.media:
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
                
            result.append(MovieOut(
                title=mov.title or "",
                original_title=getattr(mov, "originalTitle", None),
                file_name=file_name,
                file_path=file_path,
                year=mov.year,
                guids=guids
            ))
        return result
    except Exception as e:
        raise HttpError(500, f"Failed to retrieve movies from section '{section_name}': {str(e)}")
