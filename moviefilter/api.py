import json

from bs4 import BeautifulSoup
from django.db.models import Q
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError
from requests import RequestException

from movie_filter_pro.settings import DEFER, HIGH, LOW, SKIP, TRANS_FOUND, WAIT_TRANS
from moviefilter.classes import KinozalSearch
from moviefilter.hotfolder import resolve_torrents_hotfolder_path
from moviefilter.image_caching import get_cached_image_url
from moviefilter.image_caching import remove_cached_image
from moviefilter.kinozal import KinozalClient, LinkConstructor
from moviefilter.models import MovieRSS, UserPreferences


api = NinjaAPI(title="Kinozal API", version="1.0", urls_namespace="kinozal-api")

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
DEFAULT_SORT = "date_added"

PRIORITY_FILTERS = {"ALL", "HIGH", "LOW", "DEFER", "SKIP", "WAIT_TRANS", "TRANS_FOUND"}

PRIORITY_KEY_MAP = {
    HIGH: "HIGH",
    LOW: "LOW",
    DEFER: "DEFER",
    SKIP: "SKIP",
    WAIT_TRANS: "WAIT_TRANS",
    TRANS_FOUND: "TRANS_FOUND",
}

PRIORITY_DB_MAP = {value: key for key, value in PRIORITY_KEY_MAP.items()}

ALLOWED_SORTS = {
    "date_added": ("date_added", "id"),
    "title": ("title", "id"),
    "year": ("-year", "-id"),
    "imdb_rating": ("-imdb_rating", "-id"),
    "kinopoisk_rating": ("-kinopoisk_rating", "-id"),
}

ALLOWED_REVERSED_SORTS = {
    "date_added": ("-date_added", "-id"),
    "title": ("-title", "-id"),
    "year": ("year", "id"),
    "imdb_rating": ("imdb_rating", "id"),
    "kinopoisk_rating": ("kinopoisk_rating", "id"),
}


class KinozalMovieOut(Schema):
    id: int
    kinozal_id: int
    title: str
    original_title: str | None = None
    year: str
    date_added: str
    plot: str
    translate: str | None = None
    poster_url: str | None = None
    imdb_rating: float | None = None
    kinopoisk_rating: float | None = None
    priority_key: str
    priority_label: str
    kinorium_partial_match: bool
    genres: list[str]
    countries: list[str]
    directors: list[str]
    actors: list[str]
    open_url: str | None = None


class KinozalSummaryOut(Schema):
    last_scan: str | None = None
    total: int
    high: int
    low: int
    defer: int
    skip: int
    wait_trans: int
    trans_found: int


class KinozalMoviesPageOut(Schema):
    items: list[KinozalMovieOut]
    next_cursor: str | None = None
    has_more: bool
    limit: int
    total_count: int


class KinozalActionOut(Schema):
    id: int
    title: str
    previous_priority_key: str
    current_priority_key: str
    message: str


class KinozalDownloadOptionOut(Schema):
    id: int
    header: str
    size: str
    seed: str
    peer: str
    created: str
    link: str
    is_4k: bool
    is_sdr: bool


class KinozalDownloadOptionsOut(Schema):
    movie_id: int
    title: str
    items: list[KinozalDownloadOptionOut]


class KinozalTorrentDownloadOut(Schema):
    torrent_id: int
    message: str
    filename: str | None = None
    saved_to: str | None = None


def _require_api_user(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        raise HttpError(401, "Authentication required")
    return user


def _raise_kinozal_error(status: int, code: str, message: str, hint: str | None = None):
    detail = {
        "code": code,
        "message": message,
    }
    if hint:
        detail["hint"] = hint
    raise HttpError(status, json.dumps(detail, ensure_ascii=False))


@api.exception_handler(HttpError)
def kinozal_http_error_handler(request, exc: HttpError):
    try:
        message = exc.message
        detail = json.loads(message)
        if isinstance(detail, dict):
            return api.create_response(request, {"detail": detail}, status=exc.status_code)
    except (TypeError, ValueError, json.JSONDecodeError):
        pass

    return api.create_response(request, {"detail": str(exc)}, status=exc.status_code)


def _normalize_page_size(limit: int) -> int:
    if limit <= 0:
        return DEFAULT_PAGE_SIZE
    return min(limit, MAX_PAGE_SIZE)


def _require_kinozal_preferences(*, require_hotfolder: bool = False) -> UserPreferences:
    preferences = UserPreferences.get()

    if not (preferences.kinozal_domain or "").strip():
        _raise_kinozal_error(
            400,
            "settings_missing_domain",
            "Не указан домен Kinozal.",
            "Открой Preferences и заполни `kinozal_domain`.",
        )

    if not (preferences.cookie_uid or "").strip() or not (preferences.cookie_pass or "").strip():
        _raise_kinozal_error(
            400,
            "settings_missing_auth",
            "Не настроены cookies для авторизации на Kinozal.",
            "Открой Preferences и заполни `cookie_uid` и `cookie_pass`.",
        )

    if require_hotfolder and not (preferences.torrents_hotfolder or "").strip():
        _raise_kinozal_error(
            400,
            "settings_missing_hotfolder",
            "Не настроен hotfolder для torrent-файлов.",
            "На сервере в Docker обычно используется `/torrents_hotfolder`, а локально на Windows лучше указывать явный путь вроде `\\\\qnap\\TorrentsHotFolder`.",
        )

    return preferences


def _normalize_priority(priority: str | None) -> str:
    value = (priority or "ALL").strip().upper()
    if value not in PRIORITY_FILTERS:
        raise HttpError(400, "Invalid priority filter")
    return value


def _normalize_sort(sort: str | None) -> str:
    value = (sort or DEFAULT_SORT).strip()
    if value not in ALLOWED_SORTS:
        raise HttpError(400, "Invalid sort")
    return value


def _decode_cursor(cursor: str) -> int:
    try:
        offset = int(cursor)
        if offset < 0:
            raise ValueError
        return offset
    except (TypeError, ValueError) as exc:
        raise HttpError(400, "Invalid cursor") from exc


def _build_queryset(priority: str, q: str | None, sort: str, reverse: bool):
    qs = MovieRSS.objects.all()

    if priority != "ALL":
        qs = qs.filter(priority=PRIORITY_DB_MAP[priority])

    search_query = (q or "").strip()
    if search_query:
        qs = qs.filter(
            Q(title__icontains=search_query)
            | Q(original_title__icontains=search_query)
            | Q(year__icontains=search_query)
        )

    ordering = ALLOWED_REVERSED_SORTS[sort] if reverse else ALLOWED_SORTS[sort]
    return qs.order_by(*ordering)


def _normalize_poster_url(request, poster_url: str | None) -> str | None:
    if not poster_url:
        return None
    if poster_url.startswith("http://") or poster_url.startswith("https://"):
        return poster_url
    return request.build_absolute_uri(poster_url)


def _build_open_url(movie: MovieRSS) -> str | None:
    preferences = UserPreferences.get()
    if not preferences.kinozal_domain:
        return None
    return LinkConstructor(
        s=f"{movie.title} / {movie.original_title}",
        d=movie.year,
        c=1002,
        v=3,
    ).search_url()


def _serialize_movie(request, movie: MovieRSS) -> KinozalMovieOut:
    return KinozalMovieOut(
        id=movie.id,
        kinozal_id=movie.kinozal_id,
        title=movie.title,
        original_title=movie.original_title or None,
        year=movie.year,
        date_added=movie.date_added.isoformat(),
        plot=movie.plot or "",
        translate=movie.translate or None,
        poster_url=_normalize_poster_url(
            request,
            get_cached_image_url(movie.poster, movie.pk, movie.priority),
        ),
        imdb_rating=movie.imdb_rating,
        kinopoisk_rating=movie.kinopoisk_rating,
        priority_key=PRIORITY_KEY_MAP.get(movie.priority, str(movie.priority)),
        priority_label=movie.get_priority_display(),
        kinorium_partial_match=bool(movie.kinorium_partial_match),
        genres=movie.genres_as_list,
        countries=movie.countries_as_list,
        directors=movie.director_as_list,
        actors=movie.actors_as_list,
        open_url=_build_open_url(movie),
    )


def _get_movie_or_404(movie_id: int) -> MovieRSS:
    movie = MovieRSS.objects.filter(pk=movie_id).first()
    if movie is None:
        raise HttpError(404, "Movie not found")
    return movie


def _priority_key(priority: int) -> str:
    return PRIORITY_KEY_MAP.get(priority, str(priority))


def _serialize_download_option(item: KinozalSearch) -> KinozalDownloadOptionOut:
    return KinozalDownloadOptionOut(
        id=int(item.id),
        header=item.header or "",
        size=item.size or "",
        seed=str(item.seed or ""),
        peer=str(item.peer or ""),
        created=item.created or "",
        link=item.link or "",
        is_4k=bool(item.is_4k),
        is_sdr=bool(item.is_sdr),
    )


def _update_movie_priority(movie_id: int, target_priority: int, *, message_prefix: str, remove_cache: bool = False):
    movie = _get_movie_or_404(movie_id)
    previous_priority_key = _priority_key(movie.priority)

    MovieRSS.objects.filter(pk=movie_id).update(priority=target_priority)

    if remove_cache:
        remove_cached_image(movie_id)

    updated_movie = _get_movie_or_404(movie_id)
    return KinozalActionOut(
        id=updated_movie.id,
        title=updated_movie.title,
        previous_priority_key=previous_priority_key,
        current_priority_key=_priority_key(updated_movie.priority),
        message=f"{message_prefix}: '{updated_movie.title}'",
    )


def _download_torrent_file(torrent_id: int) -> tuple[str | None, str, str]:
    preferences = _require_kinozal_preferences(require_hotfolder=True)
    client = KinozalClient()
    configured_destination = preferences.torrents_hotfolder or ""
    resolved_destination = resolve_torrents_hotfolder_path(configured_destination)

    try:
        response = client.download_torrent(torrent_id)
    except RequestException as exc:
        _raise_kinozal_error(
            502,
            "kinozal_unreachable",
            "Не удалось связаться с Kinozal при скачивании torrent-файла.",
            str(exc),
        )

    out_of_torrent_number_message = "Вам недоступен торрент-файл для скачивания"

    if response.headers.get("Content-Type") != "application/x-bittorrent":
        body = response.content.decode("windows-1251", errors="ignore")
        if out_of_torrent_number_message in body:
            _raise_kinozal_error(
                409,
                "download_limit_reached",
                "Kinozal сообщил, что дневной лимит скачиваний исчерпан.",
            )
        _raise_kinozal_error(
            502,
            "invalid_torrent_response",
            "Kinozal вернул HTML вместо torrent-файла.",
        )

    if response.status_code != 200:
        _raise_kinozal_error(
            502,
            "bad_kinozal_response",
            f"Kinozal вернул неожиданный статус: {response.status_code}.",
        )

    try:
        filename = response.headers["content-disposition"].split("=")[1].strip('"')
    except (KeyError, IndexError) as exc:
        _raise_kinozal_error(
            502,
            "missing_torrent_filename",
            "Не удалось определить имя torrent-файла из ответа Kinozal.",
        )

    try:
        resolved_destination.mkdir(parents=True, exist_ok=True)
        full_path = resolved_destination / filename
        with open(full_path, "wb") as file:
            file.write(response.content)
    except (FileNotFoundError, OSError) as exc:
        _raise_kinozal_error(
            400,
            "hotfolder_write_failed",
            "Не удалось записать torrent-файл в hotfolder.",
            f"Настройка: {configured_destination}. Реальный путь: {resolved_destination}. {exc}",
        )

    return filename, f"Torrent сохранен: {full_path}", str(full_path)


def _kinozal_search(movie_id: int) -> list[KinozalSearch]:
    preferences = _require_kinozal_preferences()
    client = KinozalClient()
    movie = _get_movie_or_404(movie_id)
    results: list[KinozalSearch] = []

    combined_titles = " / ".join([part for part in [movie.title, movie.original_title] if part])
    search_string = combined_titles if len(combined_titles) < 64 else movie.title

    try:
        year = str(int(movie.year))
    except ValueError:
        year = None

    for quality in [3, 7]:
        if year:
            link_builder = LinkConstructor(s=search_string, d=year, v=quality)
        else:
            link_builder = LinkConstructor(s=search_string, v=quality)

        try:
            response = client.get_html_response(link_builder.search_url())
        except RequestException as exc:
            _raise_kinozal_error(
                502,
                "kinozal_unreachable",
                "Не удалось получить список доступных раздач с Kinozal.",
                str(exc),
            )
        if not response.ok:
            _raise_kinozal_error(
                502,
                "kinozal_search_failed",
                f"Kinozal search failed with status {response.status_code}.",
            )

        soup = BeautifulSoup(response.content, "html.parser")
        movies_elements = soup.find_all("tr", "bg")

        for element in movies_elements:
            item = KinozalSearch()
            item.id = int(element.a["href"].split("=")[1])
            item.header = element.a.text
            item.size = element.find_all("td", "s")[1].text
            item.seed = element.find("td", {"class": "sl_s"}).text
            item.peer = element.find("td", {"class": "sl_p"}).text
            item.created = element.find_all("td", "s")[2].text
            item.link = f"https://{preferences.kinozal_domain}{element.a['href']}"
            item.is_4k = quality == 7
            item.is_sdr = "SDR" in item.header
            results.append(item)

    return results


@api.get("/summary", response=KinozalSummaryOut)
def summary(request):
    _require_api_user(request)

    preferences = UserPreferences.get()
    high = MovieRSS.objects.filter(priority=HIGH).count()
    low = MovieRSS.objects.filter(priority=LOW).count()
    defer = MovieRSS.objects.filter(priority=DEFER).count()
    skip = MovieRSS.objects.filter(priority=SKIP).count()
    wait_trans = MovieRSS.objects.filter(priority=WAIT_TRANS).count()
    trans_found = MovieRSS.objects.filter(priority=TRANS_FOUND).count()

    return KinozalSummaryOut(
        last_scan=preferences.last_scan.isoformat() if preferences.last_scan else None,
        total=high + low + defer,
        high=high,
        low=low,
        defer=defer,
        skip=skip,
        wait_trans=wait_trans,
        trans_found=trans_found,
    )


@api.get("/movies", response=KinozalMoviesPageOut)
def list_movies(
    request,
    limit: int = DEFAULT_PAGE_SIZE,
    cursor: str | None = None,
    priority: str = "ALL",
    q: str | None = None,
    sort: str = DEFAULT_SORT,
    reverse: bool = False,
):
    _require_api_user(request)

    page_size = _normalize_page_size(limit)
    normalized_priority = _normalize_priority(priority)
    normalized_sort = _normalize_sort(sort)
    offset = _decode_cursor(cursor) if cursor else 0
    qs = _build_queryset(normalized_priority, q, normalized_sort, reverse)
    total_count = qs.count()

    movies = list(qs[offset : offset + page_size + 1])
    has_more = len(movies) > page_size
    page_items = movies[:page_size]
    next_cursor = str(offset + page_size) if has_more else None

    return KinozalMoviesPageOut(
        items=[_serialize_movie(request, movie) for movie in page_items],
        next_cursor=next_cursor,
        has_more=has_more,
        limit=page_size,
        total_count=total_count,
    )


@api.post("/movies/{movie_id}/hide", response=KinozalActionOut)
def hide_movie(request, movie_id: int):
    _require_api_user(request)
    return _update_movie_priority(
        movie_id,
        SKIP,
        message_prefix="Hide",
        remove_cache=True,
    )


@api.post("/movies/{movie_id}/defer", response=KinozalActionOut)
def defer_movie(request, movie_id: int):
    _require_api_user(request)
    return _update_movie_priority(
        movie_id,
        DEFER,
        message_prefix="Defer",
    )


@api.post("/movies/{movie_id}/wait-trans", response=KinozalActionOut)
def wait_trans_movie(request, movie_id: int):
    _require_api_user(request)
    return _update_movie_priority(
        movie_id,
        WAIT_TRANS,
        message_prefix="Wait trans",
        remove_cache=True,
    )


@api.get("/movies/{movie_id}/download-options", response=KinozalDownloadOptionsOut)
def movie_download_options(request, movie_id: int):
    _require_api_user(request)
    movie = _get_movie_or_404(movie_id)
    results = _kinozal_search(movie_id)
    return KinozalDownloadOptionsOut(
        movie_id=movie.id,
        title=movie.title,
        items=[_serialize_download_option(item) for item in results],
    )


@api.post("/torrents/{torrent_id}/download", response=KinozalTorrentDownloadOut)
def download_torrent(request, torrent_id: int):
    _require_api_user(request)
    filename, message, saved_to = _download_torrent_file(torrent_id)
    return KinozalTorrentDownloadOut(
        torrent_id=torrent_id,
        filename=filename,
        message=message,
        saved_to=saved_to,
    )
