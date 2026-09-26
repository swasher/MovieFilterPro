import logging
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Exists, OuterRef, Q
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

logger = logging.getLogger("vault.tmdb_writeback")

from vault.models import (
    Collection,
    FavoritePerson,
    Genre,
    Movie,
    MoviePerson,
    Person,
    Season,
    SidebarLayout,
    TMDBSyncQueueItem,
    UserList,
    UserListMovie,
    UserMovie,
    UserSeason,
    VaultConnectionEvent,
)
from vault.services.movie_search_service import MovieSearchService
from vault.services.movie_status_service import MovieStatusService
from vault.services.season_status_service import UNSET, SeasonStatusService
from vault.services.tmdb_movie_import_service import TMDBMovieImportService
from vault.services.tmdb_movie_matching_service import TMDBCandidate
from vault.services.tmdb_movie_sync_service import TMDBMovieSyncService
from vault.services.tmdb_sync_queue_service import TMDBSyncKeysMissingError, TMDBSyncQueueService
from vault.constants import SYSTEM_LIST_LABELS


class MovieOut(Schema):
    id: int
    title: str
    original_title: str | None = None
    year: int | None = None
    slug: str
    poster_url: str | None = None
    movie_type: str | None = None
    in_watched: bool = False
    in_wont_watch: bool = False
    in_favorites: bool = False


class WritebackPerMovieOut(Schema):
    status: str  # synced|pending|error|disabled|no_tmdb_id
    last_error: str | None = None
    next_retry_at: str | None = None
    reason: str | None = None


class MovieDetailOut(Schema):
    id: int
    title: str
    original_title: str | None = None
    year: int | None = None
    slug: str
    description: str
    movie_type: str
    movie_type_display: str
    tmdb_media_type: str | None = None
    status: str
    status_display: str
    imdb_rating: float | None = None
    imdb_id: str | None = None
    kinopoisk_id: int | None = None
    tvdb_id: int | None = None
    homepage: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    duration: int | None = None
    age_rating: str | None = None
    trailer_url: str | None = None
    budget: Decimal | None = None
    tmdb_id: int | None = None
    tmdb_linked: bool
    tmdb_vote_average: float | None = None
    tmdb_vote_count: int | None = None
    tmdb_original_language: str | None = None
    omdb_imdb_rating: float | None = None
    omdb_imdb_votes: int | None = None
    omdb_rotten_tomatoes: int | None = None
    omdb_metacritic: int | None = None
    omdb_last_synced_at: str | None = None
    source: str
    source_display: str
    genres: list["NamedItemOut"]
    countries: list["NamedItemOut"]
    keywords: list[str] = []
    user_state: "UserStateOut"
    custom_lists: list["MovieUserListOut"]
    directors: list["PersonCreditOut"]
    producers: list["PersonCreditOut"] = []
    screenplays: list["PersonCreditOut"] = []
    writers: list["PersonCreditOut"] = []
    showrunners: list["PersonCreditOut"] = []
    actors: list["PersonCreditOut"]
    seasons: list["SeasonOut"] = []
    collection: "CollectionBriefOut | None" = None
    writeback: WritebackPerMovieOut | None = None


class CollectionPartOut(Schema):
    tmdb_id: int
    title: str
    original_title: str | None = None
    year: int | None = None
    poster_url: str | None = None
    in_vault: bool
    vault_slug: str | None = None


class CollectionBriefOut(Schema):
    tmdb_id: int
    name: str
    overview: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    parts: list[CollectionPartOut] = []


class NamedItemOut(Schema):
    name: str
    slug: str | None = None


class PersonCreditOut(Schema):
    id: int
    name: str
    original_name: str | None = None
    photo_url: str | None = None
    character_name: str | None = None
    is_favorite: bool = False
    popularity: float | None = None
    birth_date: str | None = None
    death_date: str | None = None


class UserStateOut(Schema):
    in_watched: bool
    in_will_watch: bool
    in_wont_watch: bool
    in_favorites: bool
    rating: int | None = None
    rated_at: str | None = None
    status_at: str | None = None
    watched_at: str | None = None
    note: str = ""
    note_at: str | None = None
    favorited_at: str | None = None


class MovieUserListOut(Schema):
    id: int
    name: str
    is_public: bool
    is_in_list: bool


class SidebarItemOut(Schema):
    id: str
    title: str
    href: str
    count: int = 0


class SidebarGroupOut(Schema):
    id: str
    title: str
    href: str = "#"
    children: list[SidebarItemOut]


class SidebarOrderIn(Schema):
    system_keys: list[str] = []
    custom_keys: list[str] = []


class SidebarOrderOut(Schema):
    system_keys: list[str]
    custom_keys: list[str]


class ConnectionEventMovieRefOut(Schema):
    id: int
    title: str
    slug: str | None = None


class ConnectionEventOut(Schema):
    id: int
    operation_id: str
    created_at: str
    source: str
    event_type: str
    level: str
    message: str
    rss_kinozal_id: int | None = None
    torrent_kinozal_id: int | None = None
    imdb_id: str | None = None
    kinopoisk_id: int | None = None
    tmdb_id: int | None = None
    movie_rss_title: str | None = None
    vault_movie: ConnectionEventMovieRefOut | None = None


class ConnectionEventsOut(Schema):
    items: list[ConnectionEventOut]


class TMDBSyncIn(Schema):
    force_rematch: bool = False


class TMDBSyncOut(Schema):
    status: str
    message: str
    updated_fields: list[str] = []
    orphan_persons_deleted: int = 0
    candidates: list["TMDBCandidateOut"] = []


class TMDBCandidateOut(Schema):
    tmdb_id: int
    media_type: str
    title: str
    original_title: str
    year: int | None = None
    score: int
    score_reasons: list[str] = []
    poster_url: str | None = None
    popularity: float | None = None
    vote_average: float | None = None
    overview: str = ""


class ToggleStatusIn(Schema):
    status_key: str


class ToggleStatusOut(Schema):
    status_key: str
    is_active: bool
    user_state: UserStateOut


class RateMovieIn(Schema):
    rating: int | None = None


class RateMovieOut(Schema):
    rating: int | None = None
    user_state: UserStateOut


class MovieCommentIn(Schema):
    text: str = ""


class MovieCommentOut(Schema):
    note: str
    user_state: UserStateOut


class DeleteMovieOut(Schema):
    message: str
    orphan_persons_deleted: int = 0


class ToggleMovieListIn(Schema):
    list_id: int


class ToggleMovieListOut(Schema):
    list_id: int
    is_in_list: bool
    custom_lists: list[MovieUserListOut]


class UserListCreateIn(Schema):
    name: str


class UserListUpdateIn(Schema):
    name: str


class UserListOut(Schema):
    id: int
    name: str


class UserListDeleteOut(Schema):
    message: str


class TMDBCandidateConfirmIn(Schema):
    tmdb_id: int
    media_type: str


class TMDBSearchOut(Schema):
    results: list[TMDBCandidateOut] = []


class TMDBImportIn(Schema):
    tmdb_id: int
    media_type: str


class TMDBImportOut(Schema):
    status: str
    message: str
    created: bool
    movie: MovieOut | None = None


class TMDBSyncQueueStateOut(Schema):
    enabled: bool
    counters: dict[str, int]  # pending, in_progress, synced, confirm, not_found, error
    total_unsynced: int  # сколько в базе вообще несинхронизированных (source=KINORIUM, tmdb_id IS NULL)
    missing_keys: list[str] = []  # незаполненные API-ключи, блокирующие старт очереди
    stop_reason: str | None = None  # причина авто-остановки очереди (фронт показывает красным тостом)


class TMDBSyncQueueItemOut(Schema):
    id: int
    movie_id: int
    movie_slug: str
    movie_title: str
    movie_original_title: str = ""
    movie_year: int | None = None
    movie_description: str = ""
    movie_poster_url: str | None = None
    movie_has_tmdb: bool = False
    snapshot_title: str
    snapshot_original_title: str
    snapshot_year: int | None = None
    state: str
    queued_at: str
    started_at: str | None = None
    finished_at: str | None = None
    result_status: str
    result_title: str
    result_original_title: str
    result_year: int | None = None
    result_tmdb_id: int | None = None
    result_media_type: str
    result_message: str
    retry_count: int


class TMDBSyncQueueItemsOut(Schema):
    items: list[TMDBSyncQueueItemOut]
    total: int


class TMDBSyncQueueEnqueueOut(Schema):
    added: int
    removed: int = 0
    total: int


class TMDBSyncQueueDeleteOut(Schema):
    deleted: int


class SeasonOut(Schema):
    id: int
    season_number: int
    title: str
    description: str
    release_date: str | None = None
    poster_url: str | None = None
    episodes_count: int
    air_year: int | None = None
    user_state: "UserSeasonStateOut"


class UserSeasonStateOut(Schema):
    watch_status: str | None = None
    rating: int | None = None


class EpisodeOut(Schema):
    id: int
    episode_number: int
    title: str
    description: str
    duration: int | None = None
    release_date: str | None = None


class SetSeasonStatusIn(Schema):
    watch_status: str | None = None
    rating: int | None = None


class SetSeasonStatusOut(Schema):
    season_id: int
    user_state: UserSeasonStateOut


class PersonMovieOut(Schema):
    id: int
    title: str
    slug: str
    year: int | None = None
    poster_url: str | None = None
    roles: list[str]
    character_names: list[str]


class PersonDetailOut(Schema):
    id: int
    name: str
    original_name: str
    tmdb_id: str | None = None
    imdb_id: str | None = None
    photo_url: str | None = None
    biography: str
    birth_date: str | None = None
    death_date: str | None = None
    country: str | None = None
    gender: str | None = None
    gender_display: str | None = None
    movies_count: int
    roles_count: int
    career_years: int
    filmography: list[PersonMovieOut]
    actor_count: int
    director_count: int
    producer_count: int
    screenplay_count: int
    writer_count: int
    showrunner_count: int
    is_favorite: bool


class TogglePersonFavoriteOut(Schema):
    is_favorite: bool


api = NinjaAPI(title="Vault API", version="1.0")


def _resolve_api_user(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user
    return None


def _require_api_user(request):
    user = _resolve_api_user(request)
    if user is None:
        raise HttpError(401, "Authentication required")
    return user


def _build_user_state(user, movie) -> UserStateOut:
    if user is None:
        return UserStateOut(
            in_watched=False,
            in_will_watch=False,
            in_wont_watch=False,
            in_favorites=False,
            rating=None,
            note="",
        )

    state = MovieStatusService.get_movie_status(user, movie)
    return UserStateOut(
        in_watched=state["in_watched"],
        in_will_watch=state["in_will_watch"],
        in_wont_watch=state["in_wont_watch"],
        in_favorites=state["in_favorites"],
        rating=state["rating"],
        rated_at=_date_to_iso(state["rated_at"]),
        status_at=_date_to_iso(state["status_at"]),
        watched_at=_date_to_iso(state["watched_at"]),
        note=state["note"],
        note_at=_date_to_iso(state["note_at"]),
        favorited_at=_date_to_iso(state["favorited_at"]),
    )


def _decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _date_to_iso(value) -> str | None:
    return value.isoformat() if value else None


def _datetime_to_iso(value) -> str | None:
    return value.isoformat() if value else None


def _tmdb_image_url(raw_path: str | None, size: str = "w342") -> str | None:
    if not raw_path:
        return None
    value = str(raw_path).strip()
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        return value

    base_url = getattr(settings, "TMDB_IMAGE_BASE_URL", "https://image.tmdb.org/t/p/")
    if not base_url.endswith("/"):
        base_url += "/"
    normalized_size = str(size).strip("/") or "w342"
    normalized_path = value if value.startswith("/") else f"/{value}"
    return f"{base_url}{normalized_size}{normalized_path}"


def _build_movie_user_lists(user, movie) -> list[MovieUserListOut]:
    if user is None:
        return []

    user_lists = list(UserList.objects.filter(user=user).order_by("-updated_at"))
    movie_list_ids = set(
        UserListMovie.objects.filter(movie=movie, user_list__user=user).values_list("user_list_id", flat=True)
    )
    return [
        MovieUserListOut(
            id=user_list.id,
            name=user_list.name,
            is_public=user_list.is_public,
            is_in_list=user_list.id in movie_list_ids,
        )
        for user_list in user_lists
    ]


def _build_tmdb_sync_out(result) -> TMDBSyncOut:
    return TMDBSyncOut(
        status=result.status,
        message=result.message,
        updated_fields=list(result.updated_fields),
        orphan_persons_deleted=result.orphan_persons_deleted,
        candidates=[_build_tmdb_candidate_out(item) for item in result.candidates],
    )


def _build_tmdb_candidate_out(item) -> TMDBCandidateOut:
    return TMDBCandidateOut(
        tmdb_id=item.tmdb_id,
        media_type=item.media_type,
        title=item.title,
        original_title=item.original_title,
        year=item.year,
        score=item.score,
        score_reasons=list(item.score_reasons),
        poster_url=_tmdb_image_url(item.poster_path),
        popularity=item.popularity,
        vote_average=item.vote_average,
        overview=getattr(item, "overview", None) or "",
    )


def _build_connection_event_out(item: VaultConnectionEvent) -> ConnectionEventOut:
    vault_movie = None
    if item.vault_movie_id:
        vault_movie = ConnectionEventMovieRefOut(
            id=item.vault_movie.id,
            title=item.vault_movie.title,
            slug=item.vault_movie.slug,
        )
    return ConnectionEventOut(
        id=item.id,
        operation_id=str(item.operation_id),
        created_at=_datetime_to_iso(item.created_at) or "",
        source=item.source,
        event_type=item.event_type,
        level=item.level,
        message=item.message,
        rss_kinozal_id=item.rss_kinozal_id,
        torrent_kinozal_id=item.torrent_kinozal_id,
        imdb_id=item.imdb_id,
        kinopoisk_id=item.kinopoisk_id,
        tmdb_id=item.tmdb_id,
        movie_rss_title=item.movie_rss.title if item.movie_rss_id else None,
        vault_movie=vault_movie,
    )


def _build_movie_out(movie: Movie, user=None) -> MovieOut:
    in_watched = False
    in_wont_watch = False
    in_favorites = False
    if user is not None:
        state = MovieStatusService.get_movie_status(user, movie)
        in_watched = state["in_watched"]
        in_wont_watch = state["in_wont_watch"]
        in_favorites = state["in_favorites"]
    return MovieOut(
        id=movie.id,
        title=movie.title,
        original_title=movie.original_title,
        year=movie.year,
        slug=movie.slug,
        poster_url=movie.poster_url,
        movie_type=movie.movie_type,
        in_watched=in_watched,
        in_wont_watch=in_wont_watch,
        in_favorites=in_favorites,
    )


def _ui_status_display(movie: Movie) -> str:
    """Статус для UI: сериал в статусе released (между сезонами) показываем как «ПАУЗА»."""
    if movie.movie_type == Movie.MovieType.SERIES and movie.status == Movie.Status.RELEASED:
        return "ПАУЗА"
    return movie.get_status_display()


def _build_season_out(season: Season, user=None) -> SeasonOut:
    episodes_count = season.episodes.count()
    release_date = season.release_date
    air_year = release_date.year if release_date else None

    user_state_data = {"watch_status": None, "rating": None}
    if user is not None:
        user_state_data = SeasonStatusService.get_season_state(user, season)

    return SeasonOut(
        id=season.id,
        season_number=season.season_number,
        title=season.title,
        description=season.description,
        release_date=_date_to_iso(season.release_date),
        poster_url=_tmdb_image_url(season.poster),
        episodes_count=episodes_count,
        air_year=air_year,
        user_state=UserSeasonStateOut(
            watch_status=user_state_data["watch_status"],
            rating=user_state_data["rating"],
        ),
    )


def _build_collection_out(movie: Movie) -> CollectionBriefOut | None:
    """Собирает CollectionBriefOut из movie.collection + parts_data. in_vault вычисляется на лету."""
    coll: Collection | None = getattr(movie, "collection", None)
    # Если relation не загружен — пробуем по FK
    if coll is None and getattr(movie, "collection_id", None):
        try:
            coll = Collection.objects.filter(id=movie.collection_id).first()
        except Exception:
            coll = None
    if coll is None:
        return None

    parts_raw: list[dict] = list(coll.parts_data or [])
    # Собираем карту tmdb_id -> Movie (slug) одним запросом
    tmdb_ids = [p.get("tmdb_id") for p in parts_raw if p.get("tmdb_id") is not None]
    vault_map: dict[int, str] = {}
    if tmdb_ids:
        try:
            # Фильтруем только те tmdb_id что в parts, чтобы не тянуть всё
            for m in Movie.objects.filter(tmdb_id__in=tmdb_ids).values("tmdb_id", "slug"):
                try:
                    vault_map[int(m["tmdb_id"])] = m["slug"]
                except Exception:
                    continue
        except Exception:
            vault_map = {}

    parts_out: list[CollectionPartOut] = []
    for p in parts_raw:
        try:
            tmdb_id = int(p.get("tmdb_id"))
        except Exception:
            continue
        slug = vault_map.get(tmdb_id)
        poster_url = _tmdb_image_url(p.get("poster_path"), size="w342") if p.get("poster_path") else None
        parts_out.append(
            CollectionPartOut(
                tmdb_id=tmdb_id,
                title=str(p.get("title") or "").strip() or f"TMDB {tmdb_id}",
                original_title=str(p.get("original_title") or "").strip() or None,
                year=p.get("year"),
                poster_url=poster_url,
                in_vault=tmdb_id in vault_map,
                vault_slug=slug,
            )
        )

    return CollectionBriefOut(
        tmdb_id=coll.tmdb_id,
        name=coll.name,
        overview=coll.overview or None,
        poster_url=_tmdb_image_url(coll.poster_path, size="w342") if coll.poster_path else None,
        backdrop_url=_tmdb_image_url(coll.backdrop_path, size="w780") if coll.backdrop_path else None,
        parts=parts_out,
    )


def _build_writeback_out(movie: Movie) -> WritebackPerMovieOut | None:
    try:
        from vault.services.tmdb_writeback_service import TmdbWritebackService

        data = TmdbWritebackService.get_writeback_status(movie)
        return WritebackPerMovieOut(
            status=data.get("status", "unknown"),
            last_error=data.get("last_error"),
            next_retry_at=data.get("next_retry_at"),
            reason=data.get("reason"),
        )
    except Exception:
        return None


@api.get("/movies", response=list[MovieOut])
def list_movies(
    request,
    limit: int = 50,
    offset: int = 0,
    genre: str | None = None,
    status: str | None = None,
    list: int | None = None,
    q: str | None = None,
    search_plot: bool = False,
    order: str = "-year",
    year_from: int | None = None,
    year_to: int | None = None,
    movie_type: str | None = None,
    is_favorite: bool | None = None,
    watch_status: str | None = None,
):
    user = _resolve_api_user(request)
    qs = Movie.objects.all()

    if genre:
        genre_slugs = [g.strip() for g in genre.split(",") if g.strip()]
        if genre_slugs:
            qs = qs.filter(genres__slug__in=genre_slugs).distinct()
    # Гибридный поиск: базовый (title only, без стемминга) / расширенный (title+plot с FTS, стемминг, веса A/B, rank)
    # Для коротких паттернов (<2) и стоп-слов MovieSearchService не аннотирует rank — has_search_rank остаётся False
    has_search_rank = False
    if q:
        raw_q = (q or "").strip()
        if raw_q:
            # rank возможен только если search_plot и postgres и длина достаточна для селективного FTS/trigram
            wants_rank = bool(search_plot and MovieSearchService._is_postgres() and len(raw_q) >= 2)
            qs = MovieSearchService.apply_search(qs, raw_q, search_plot)
            # Проверяем, действительно ли queryset получил аннотацию rank (стоп-слова -> нет rank)
            has_search_rank = wants_rank and "rank" in getattr(qs.query, "annotations", {})
    if year_from is not None:
        qs = qs.filter(year__gte=year_from)
    if year_to is not None:
        qs = qs.filter(year__lte=year_to)
    if movie_type:
        qs = qs.filter(movie_type=movie_type)
    if user and status:
        if status == "favorites":
            qs = qs.filter(user_movies__user=user, user_movies__is_favorite=True)
        elif status == "watched":
            qs = qs.filter(user_movies__user=user, user_movies__watch_status=UserMovie.WatchStatus.WATCHED)
        elif status == "will_watch":
            qs = qs.filter(user_movies__user=user, user_movies__watch_status=UserMovie.WatchStatus.PLAN)
        elif status == "wont_watch":
            qs = qs.filter(user_movies__user=user, user_movies__watch_status=UserMovie.WatchStatus.SKIP)
    if user and is_favorite:
        qs = qs.filter(user_movies__user=user, user_movies__is_favorite=True)
    if user and watch_status:
        if watch_status == "watched":
            qs = qs.filter(user_movies__user=user, user_movies__watch_status=UserMovie.WatchStatus.WATCHED)
        elif watch_status == "not_watched":
            qs = qs.exclude(user_movies__user=user, user_movies__watch_status=UserMovie.WatchStatus.WATCHED)
    if user and list:
        qs = qs.filter(in_lists__user_list_id=list, in_lists__user_list__user=user)

    allowed_orders = {
        "-year": ("-year", "title", "id"),
        "year": ("year", "title", "id"),
        "-imdb_rating": ("-imdb_rating", "title", "id"),
        "imdb_rating": ("imdb_rating", "title", "id"),
        "title": ("title", "id"),
        "-title": ("-title", "id"),
    }
    if order in {"-added_at", "added_at"}:
        if user and list:
            ordering = (
                ("-in_lists__added_at", "-year", "title", "id")
                if order == "-added_at"
                else ("in_lists__added_at", "-year", "title", "id")
            )
        elif user and status:
            ordering = (
                ("-user_movies__created_at", "-year", "title", "id")
                if order == "-added_at"
                else ("user_movies__created_at", "-year", "title", "id")
            )
        else:
            ordering = (
                ("-created_at", "-year", "title", "id")
                if order == "-added_at"
                else ("created_at", "-year", "title", "id")
            )
    else:
        ordering = allowed_orders.get(order, allowed_orders["-year"])

    bounded_limit = max(1, min(limit, 100))
    bounded_offset = max(0, offset)

    # В расширенном режиме (search_plot + FTS) ранжирование по релевантности выше вторичной сортировки
    # Веса SearchVector: title/original_title = A, description = B => заголовки выше сюжета
    if has_search_rank:
        qs = qs.order_by("-rank", *ordering).distinct()[bounded_offset:bounded_offset + bounded_limit]
    else:
        qs = qs.order_by(*ordering).distinct()[bounded_offset:bounded_offset + bounded_limit]
    return [_build_movie_out(movie, user=user) for movie in qs]


@api.get("/genres", response=list[NamedItemOut])
def genre_list(request):
    return [
        NamedItemOut(name=genre.name, slug=genre.slug)
        for genre in Genre.objects.all().order_by("name")
    ]


class UserListOutShort(Schema):
    id: int
    name: str


@api.get("/lists", response=list[UserListOutShort])
def user_lists(request):
    _require_api_user(request)
    user = _resolve_api_user(request)
    if user is None:
        return []
    return [
        UserListOutShort(id=lst.id, name=lst.name)
        for lst in UserList.objects.filter(user=user).order_by("-updated_at", "id")
    ]


@api.get("/movies/{slug}", response=MovieDetailOut)
def movie_detail(request, slug: str):
    movie = Movie.objects.select_related("collection").filter(slug=slug).first()
    if movie is None:
        raise HttpError(404, "Movie not found")
    user = _resolve_api_user(request)

    favorite_person_ids = set()
    if user is not None:
        favorite_person_ids = set(
            FavoritePerson.objects.filter(user=user).values_list("person_id", flat=True)
        )

    return MovieDetailOut(
        id=movie.id,
        title=movie.title,
        original_title=movie.original_title,
        year=movie.year,
        slug=movie.slug,
        description=movie.description or "",
        movie_type=movie.movie_type,
        movie_type_display=movie.get_movie_type_display(),
        tmdb_media_type=movie.tmdb_media_type,
        status=movie.status,
        status_display=_ui_status_display(movie),
        imdb_rating=_decimal_to_float(movie.imdb_rating),
        imdb_id=movie.imdb_id or None,
        kinopoisk_id=movie.kinopoisk_id or None,
        tvdb_id=movie.tvdb_id or None,
        homepage=movie.homepage or None,
        poster_url=movie.poster_url,
        backdrop_url=movie.backdrop_url,
        duration=movie.duration,
        age_rating=movie.age_rating or None,
        trailer_url=movie.trailer_url or None,
        budget=_decimal_to_float(movie.budget),
        tmdb_id=movie.tmdb_id,
        tmdb_linked=bool(movie.tmdb_id),
        tmdb_vote_average=_decimal_to_float(movie.tmdb_vote_average),
        tmdb_vote_count=movie.tmdb_vote_count,
        tmdb_original_language=movie.tmdb_original_language,
        omdb_imdb_rating=_decimal_to_float(movie.omdb_imdb_rating),
        omdb_imdb_votes=movie.omdb_imdb_votes,
        omdb_rotten_tomatoes=movie.omdb_rotten_tomatoes,
        omdb_metacritic=movie.omdb_metacritic,
        omdb_last_synced_at=_datetime_to_iso(movie.omdb_last_synced_at),
        source=movie.source,
        source_display=movie.get_source_display(),
        genres=[
            NamedItemOut(name=genre.name, slug=genre.slug)
            for genre in movie.genres.all().order_by("name")
        ],
        countries=[
            NamedItemOut(name=country.name)
            for country in movie.countries.all().order_by("name")
        ],
        keywords=movie.keywords or [],
        user_state=_build_user_state(user, movie),
        custom_lists=_build_movie_user_lists(user, movie),
        directors=[
            PersonCreditOut(
                id=item.person.id,
                name=item.person.name,
                original_name=item.person.original_name or None,
                photo_url=item.person.photo_url,
                is_favorite=item.person.id in favorite_person_ids,
                popularity=item.popularity,
                birth_date=_date_to_iso(item.person.birth_date),
                death_date=_date_to_iso(item.person.death_date),
            )
            for item in movie.get_directors().select_related("person")
        ],
        producers=[
            PersonCreditOut(
                id=item.person.id,
                name=item.person.name,
                original_name=item.person.original_name or None,
                photo_url=item.person.photo_url,
                is_favorite=item.person.id in favorite_person_ids,
                popularity=item.popularity,
                birth_date=_date_to_iso(item.person.birth_date),
                death_date=_date_to_iso(item.person.death_date),
            )
            for item in movie.get_producers().select_related("person")
        ],
        screenplays=[
            PersonCreditOut(
                id=item.person.id,
                name=item.person.name,
                original_name=item.person.original_name or None,
                photo_url=item.person.photo_url,
                is_favorite=item.person.id in favorite_person_ids,
                popularity=item.popularity,
                birth_date=_date_to_iso(item.person.birth_date),
                death_date=_date_to_iso(item.person.death_date),
            )
            for item in movie.get_screenplays().select_related("person")
        ],
        writers=[
            PersonCreditOut(
                id=item.person.id,
                name=item.person.name,
                original_name=item.person.original_name or None,
                photo_url=item.person.photo_url,
                is_favorite=item.person.id in favorite_person_ids,
                popularity=item.popularity,
                birth_date=_date_to_iso(item.person.birth_date),
                death_date=_date_to_iso(item.person.death_date),
            )
            for item in movie.get_writers().select_related("person")
        ],
        showrunners=[
            PersonCreditOut(
                id=item.person.id,
                name=item.person.name,
                original_name=item.person.original_name or None,
                photo_url=item.person.photo_url,
                is_favorite=item.person.id in favorite_person_ids,
                popularity=item.popularity,
                birth_date=_date_to_iso(item.person.birth_date),
                death_date=_date_to_iso(item.person.death_date),
            )
            for item in movie.get_showrunners().select_related("person")
        ],
        actors=[
            PersonCreditOut(
                id=item.person.id,
                name=item.person.name,
                original_name=item.person.original_name or None,
                photo_url=item.person.photo_url,
                character_name=item.character_name or None,
                is_favorite=item.person.id in favorite_person_ids,
                popularity=item.popularity,
                birth_date=_date_to_iso(item.person.birth_date),
                death_date=_date_to_iso(item.person.death_date),
            )
            for item in movie.get_actors().select_related("person")[:12]
        ],
        seasons=[
            _build_season_out(season, user=user)
            for season in movie.seasons.all().order_by("season_number")
        ],
        collection=_build_collection_out(movie),
        writeback=_build_writeback_out(movie),
    )


# ------------------------------------ #
#          SEASONS & EPISODES          #
# ------------------------------------ #

@api.get("/movies/{slug}/seasons", response=list[SeasonOut])
def movie_seasons(request, slug: str):
    movie = Movie.objects.filter(slug=slug).first()
    if movie is None:
        raise HttpError(404, "Movie not found")
    user = _resolve_api_user(request)
    return [
        _build_season_out(season, user=user)
        for season in movie.seasons.all().order_by("season_number")
    ]


@api.get("/seasons/{season_id}/episodes", response=list[EpisodeOut])
def season_episodes(request, season_id: int):
    season = Season.objects.filter(id=season_id).first()
    if season is None:
        raise HttpError(404, "Season not found")
    return [
        EpisodeOut(
            id=episode.id,
            episode_number=episode.episode_number,
            title=episode.title,
            description=episode.description,
            duration=episode.duration,
            release_date=_date_to_iso(episode.release_date),
        )
        for episode in season.episodes.all().order_by("episode_number")
    ]


@api.patch("/seasons/{season_id}/status", response=SetSeasonStatusOut)
def season_toggle_status(request, season_id: int, payload: SetSeasonStatusIn):
    season = Season.objects.filter(id=season_id).first()
    if season is None:
        raise HttpError(404, "Season not found")

    user = _require_api_user(request)

    changes = payload.model_dump(exclude_unset=True)

    try:
        obj = SeasonStatusService.set_season_status(
            user=user,
            season=season,
            watch_status=changes.get("watch_status", UNSET),
            rating=changes.get("rating", UNSET),
        )
    except ValueError as exc:
        raise HttpError(400, str(exc))

    state = SeasonStatusService.get_season_state(user, season)
    return SetSeasonStatusOut(
        season_id=season.id,
        user_state=UserSeasonStateOut(
            watch_status=state["watch_status"],
            rating=state["rating"],
        ),
    )


@api.post("/movies/{slug}/fetch-tmdb", response=TMDBSyncOut)
def movie_fetch_tmdb(request, slug: str, payload: TMDBSyncIn):
    movie = Movie.objects.filter(slug=slug).first()
    if movie is None:
        raise HttpError(404, "Movie not found")

    try:
        result = TMDBMovieSyncService.sync_movie(
            movie=movie,
            force_rematch=payload.force_rematch,
        )
    except Exception as exc:
        raise HttpError(400, TMDBMovieSyncService.describe_exception(exc))

    # §20.1: после успешного READ-синка сразу пушим локальные статусы в TMDB (точечно, без bulk)
    if getattr(result, "status", None) == "ok":
        try:
            user = _resolve_api_user(request)
            if user and movie.tmdb_id:
                # movie мог обновиться внутри sync_movie — перечитать tmdb_id на всякий
                movie.refresh_from_db(fields=["tmdb_id", "tmdb_media_type"])
                um = UserMovie.objects.filter(user=user, movie=movie).first()
                if um:
                    from vault.services.tmdb_writeback_service import TmdbWritebackService

                    TmdbWritebackService.sync_user_movie_to_tmdb(um)
        except Exception as exc:
            logger.warning("Writeback post-fetch failed for movie %s: %s", movie.slug, exc, exc_info=True)

    return _build_tmdb_sync_out(result)


@api.post("/movies/{slug}/fetch-tmdb-confirm", response=TMDBSyncOut)
def movie_fetch_tmdb_confirm(request, slug: str, payload: TMDBCandidateConfirmIn):
    movie = Movie.objects.filter(slug=slug).first()
    if movie is None:
        raise HttpError(404, "Movie not found")

    media_type = (payload.media_type or "").strip().lower()
    if media_type not in {"movie", "tv"}:
        raise HttpError(400, "Invalid media_type")

    candidate = TMDBCandidate(
        tmdb_id=payload.tmdb_id,
        media_type=media_type,
        title="",
        original_title="",
        year=None,
        score=0,
        score_reasons=("manual_choice",),
        poster_path=None,
        popularity=None,
        vote_average=None,
    )

    try:
        result = TMDBMovieSyncService.sync_movie(
            movie=movie,
            force_rematch=True,
            selected_candidate=candidate,
        )
    except Exception as exc:
        raise HttpError(400, TMDBMovieSyncService.describe_exception(exc))

    # §20.1: confirm также пушит
    if getattr(result, "status", None) == "ok":
        try:
            user = _resolve_api_user(request)
            if user and movie.tmdb_id:
                movie.refresh_from_db(fields=["tmdb_id", "tmdb_media_type"])
                um = UserMovie.objects.filter(user=user, movie=movie).first()
                if um:
                    from vault.services.tmdb_writeback_service import TmdbWritebackService

                    TmdbWritebackService.sync_user_movie_to_tmdb(um)
        except Exception as exc:
            logger.warning("Writeback post-fetch-confirm failed for movie %s: %s", movie.slug, exc, exc_info=True)

    return _build_tmdb_sync_out(result)


@api.get("/tmdb/search", response=TMDBSearchOut)
def tmdb_search(request, q: str, limit: int = 10):
    _require_api_user(request)

    try:
        results = TMDBMovieImportService.search_movies(q, limit=limit)
    except Exception as exc:
        raise HttpError(400, str(exc))

    return TMDBSearchOut(results=[_build_tmdb_candidate_out(item) for item in results])


@api.get("/tmdb/lookup", response=TMDBCandidateOut)
def tmdb_lookup(request, tmdb_id: int, media_type: str | None = None):
    _require_api_user(request)

    try:
        candidate = TMDBMovieImportService.lookup_by_id(tmdb_id, media_type=media_type)
    except Exception as exc:
        raise HttpError(400, str(exc))

    if candidate is None:
        raise HttpError(404, "TMDB ID не найден")

    return _build_tmdb_candidate_out(candidate)


class TMDBLookupAnyOut(Schema):
    movie: TMDBCandidateOut | None = None
    tv: TMDBCandidateOut | None = None


@api.get("/tmdb/lookup-any", response=TMDBLookupAnyOut)
def tmdb_lookup_any(request, tmdb_id: int):
    """Пакетный lookup для диалога Link TMDB: ищет ID и как movie, и как tv.

    Всегда отвечает 200 (кандидаты или null), чтобы фронт не слал два
    параллельных запроса, один из которых заведомо падает в 404 и шумит
    в консоли браузера. Старый /tmdb/lookup не тронут.
    """
    _require_api_user(request)

    movie_out: TMDBCandidateOut | None = None
    tv_out: TMDBCandidateOut | None = None
    try:
        movie_candidate = TMDBMovieImportService.lookup_by_id(tmdb_id, media_type="movie")
        if movie_candidate is not None:
            movie_out = _build_tmdb_candidate_out(movie_candidate)
    except Exception as exc:
        raise HttpError(400, str(exc))
    try:
        tv_candidate = TMDBMovieImportService.lookup_by_id(tmdb_id, media_type="tv")
        if tv_candidate is not None:
            tv_out = _build_tmdb_candidate_out(tv_candidate)
    except Exception as exc:
        raise HttpError(400, str(exc))

    return TMDBLookupAnyOut(movie=movie_out, tv=tv_out)


@api.get("/connection-events", response=ConnectionEventsOut)
def connection_events(
    request,
    limit: int = 100,
    level: str | None = None,
    source: str | None = None,
    movie_rss_id: int | None = None,
    operation_id: str | None = None,
):
    _require_api_user(request)

    bounded_limit = max(1, min(limit, 200))
    qs = VaultConnectionEvent.objects.select_related("movie_rss", "vault_movie").order_by("-created_at", "-id")

    if level:
        qs = qs.filter(level=level.strip().lower())
    if source:
        qs = qs.filter(source=source.strip())
    if movie_rss_id:
        qs = qs.filter(movie_rss_id=movie_rss_id)
    if operation_id:
        qs = qs.filter(operation_id=operation_id.strip())

    return ConnectionEventsOut(items=[_build_connection_event_out(item) for item in qs[:bounded_limit]])


@api.post("/tmdb/import", response=TMDBImportOut)
def tmdb_import(request, payload: TMDBImportIn):
    _require_api_user(request)

    try:
        result = TMDBMovieImportService.import_movie(
            tmdb_id=payload.tmdb_id,
            media_type=payload.media_type,
        )
    except Exception as exc:
        raise HttpError(400, str(exc))

    return TMDBImportOut(
        status=result.status,
        message=result.message,
        created=result.status == "created",
        movie=_build_movie_out(result.movie),
    )


@api.post("/movies/{slug}/toggle-status", response=ToggleStatusOut)
def movie_toggle_status(request, slug: str, payload: ToggleStatusIn):
    movie = Movie.objects.filter(slug=slug).first()
    if movie is None:
        raise HttpError(404, "Movie not found")

    user = _require_api_user(request)

    try:
        is_active = MovieStatusService.toggle_status(user, movie, payload.status_key)
    except Exception as exc:
        raise HttpError(400, str(exc))

    return ToggleStatusOut(
        status_key=payload.status_key,
        is_active=is_active,
        user_state=_build_user_state(user, movie),
    )


@api.post("/movies/{slug}/toggle-list", response=ToggleMovieListOut)
def movie_toggle_list(request, slug: str, payload: ToggleMovieListIn):
    movie = Movie.objects.filter(slug=slug).first()
    if movie is None:
        raise HttpError(404, "Movie not found")

    user = _require_api_user(request)

    user_list = UserList.objects.filter(id=payload.list_id, user=user).first()
    if user_list is None:
        raise HttpError(404, "List not found")

    relation = UserListMovie.objects.filter(user_list=user_list, movie=movie).first()
    if relation:
        relation.delete()
        is_in_list = False
    else:
        UserListMovie.objects.create(user_list=user_list, movie=movie)
        is_in_list = True

    return ToggleMovieListOut(
        list_id=user_list.id,
        is_in_list=is_in_list,
        custom_lists=_build_movie_user_lists(user, movie),
    )


@api.post("/movies/{slug}/rate", response=RateMovieOut)
def movie_rate(request, slug: str, payload: RateMovieIn):
    movie = Movie.objects.filter(slug=slug).first()
    if movie is None:
        raise HttpError(404, "Movie not found")

    user = _require_api_user(request)

    try:
        if payload.rating is None:
            MovieStatusService.remove_rating(user, movie)
        else:
            MovieStatusService.rate_movie(user, movie, payload.rating)
    except Exception as exc:
        raise HttpError(400, str(exc))

    state = _build_user_state(user, movie)
    return RateMovieOut(
        rating=state.rating,
        user_state=state,
    )


@api.patch("/movies/{slug}/comment", response=MovieCommentOut)
def movie_comment_save(request, slug: str, payload: MovieCommentIn):
    """Сохранить (создать/обновить) комментарий пользователя к фильму."""
    movie = Movie.objects.filter(slug=slug).first()
    if movie is None:
        raise HttpError(404, "Movie not found")

    user = _require_api_user(request)

    MovieStatusService.set_note(user, movie, payload.text)

    user_state = _build_user_state(user, movie)
    return MovieCommentOut(note=user_state.note, user_state=user_state)


@api.delete("/movies/{slug}/comment", response=MovieCommentOut)
def movie_comment_delete(request, slug: str):
    """Удалить комментарий пользователя к фильму."""
    movie = Movie.objects.filter(slug=slug).first()
    if movie is None:
        raise HttpError(404, "Movie not found")

    user = _require_api_user(request)

    MovieStatusService.clear_note(user, movie)

    user_state = _build_user_state(user, movie)
    return MovieCommentOut(note=user_state.note, user_state=user_state)


@api.post("/movies/{slug}/delete", response=DeleteMovieOut)
def movie_delete(request, slug: str):
    movie = Movie.objects.filter(slug=slug).first()
    if movie is None:
        raise HttpError(404, "Movie not found")

    _require_api_user(request)

    movie.delete()
    orphan_persons_deleted = TMDBMovieSyncService._cleanup_orphan_persons()
    return DeleteMovieOut(
        message="Фильм удален из Vault",
        orphan_persons_deleted=orphan_persons_deleted,
    )


@api.get("/persons/{person_id}", response=PersonDetailOut)
def person_detail(request, person_id: int):
    person = Person.objects.filter(id=person_id).first()
    if person is None:
        raise HttpError(404, "Person not found")

    user = _resolve_api_user(request)
    is_favorite = False
    if user is not None:
        is_favorite = FavoritePerson.objects.filter(user=user, person=person).exists()

    filmography_qs = (
        MoviePerson.objects.filter(person=person)
        .select_related("movie")
        .order_by("-movie__year", "order", "id")
    )

    grouped: dict[int, dict] = {}
    for item in filmography_qs:
        movie = item.movie
        entry = grouped.get(movie.id)
        if entry is None:
            entry = {
                "id": movie.id,
                "title": movie.title,
                "slug": movie.slug,
                "year": movie.year,
                "poster_url": movie.poster_url,
                "roles": [],
                "character_names": [],
            }
            grouped[movie.id] = entry
        role_display = item.get_role_display()
        if role_display not in entry["roles"]:
            entry["roles"].append(role_display)
        if item.character_name and item.character_name not in entry["character_names"]:
            entry["character_names"].append(item.character_name)

    filmography = [PersonMovieOut(**data) for data in grouped.values()]

    years = [item.movie.year for item in filmography_qs if item.movie.year is not None]

    return PersonDetailOut(
        id=person.id,
        name=person.name,
        original_name=person.original_name,
        tmdb_id=person.tmdb_id,
        imdb_id=person.imdb_id,
        photo_url=person.photo_url,
        biography=person.biography or "",
        birth_date=_date_to_iso(person.birth_date),
        death_date=_date_to_iso(person.death_date),
        country=person.country.name if person.country_id else None,
        gender=person.gender or None,
        gender_display=person.get_gender_display() if person.gender else None,
        movies_count=len(filmography),
        roles_count=filmography_qs.values("role").distinct().count(),
        career_years=(max(years) - min(years)) if years else 0,
        filmography=filmography,
        actor_count=filmography_qs.filter(role="actor").count(),
        director_count=filmography_qs.filter(role="director").count(),
        producer_count=filmography_qs.filter(role="producer").count(),
        screenplay_count=filmography_qs.filter(role="screenplay").count(),
        writer_count=filmography_qs.filter(role="writer").count(),
        showrunner_count=filmography_qs.filter(role="showrunner").count(),
        is_favorite=is_favorite,
    )


@api.post("/persons/{person_id}/toggle-favorite", response=TogglePersonFavoriteOut)
def person_toggle_favorite(request, person_id: int):
    person = Person.objects.filter(id=person_id).first()
    if person is None:
        raise HttpError(404, "Person not found")

    user = _require_api_user(request)

    favorite, created = FavoritePerson.objects.get_or_create(user=user, person=person)
    if not created:
        favorite.delete()

    return TogglePersonFavoriteOut(is_favorite=created)


SYSTEM_SIDEBAR_KEYS = list(SYSTEM_LIST_LABELS.keys())

SYSTEM_SIDEBAR_ITEMS = [
    SidebarItemOut(id=key, title=label, href=f"/?status={key}", count=0)
    for key, label in SYSTEM_LIST_LABELS.items()
]


def _order_system_keys(stored_keys: list[str]) -> list[str]:
    stored = list(dict.fromkeys(key for key in stored_keys if key in SYSTEM_SIDEBAR_KEYS))
    return stored + [key for key in SYSTEM_SIDEBAR_KEYS if key not in stored]


def _order_custom_keys(stored_keys: list[str], custom_items: list[SidebarItemOut]) -> list[SidebarItemOut]:
    by_id = {item.id: item for item in custom_items}
    stored = list(dict.fromkeys(key for key in stored_keys if key in by_id))
    ordered = [by_id[key] for key in stored]
    ordered.extend(item for item in custom_items if item.id not in stored)
    return ordered


@api.get("/sidebar", response=list[SidebarGroupOut])
def sidebar_data(request):
    user = _resolve_api_user(request)
    if user is None:
        return [
            SidebarGroupOut(
                id="system",
                title="Системные",
                children=SYSTEM_SIDEBAR_ITEMS,
            ),
            SidebarGroupOut(id="custom", title="Мои списки", children=[]),
        ]

    counts = MovieStatusService.get_system_lists_counts(user)

    system_items = [
        SidebarItemOut(
            id=item.id,
            title=item.title,
            href=item.href,
            count=counts[item.id],
        )
        for item in SYSTEM_SIDEBAR_ITEMS
    ]

    custom_lists_qs = (
        UserList.objects.filter(user=user)
        .annotate(movies_count=Count("list_movies"))
        .order_by("-updated_at", "id")
    )
    custom_items = [
        SidebarItemOut(
            id=f"list_{item.id}",
            title=item.name,
            href=f"/?list={item.id}",
            count=item.movies_count,
        )
        for item in custom_lists_qs
    ]

    layout = SidebarLayout.objects.filter(user=user).first()
    if layout is not None:
        system_keys = _order_system_keys(layout.system_keys or [])
        custom_items = _order_custom_keys(layout.custom_keys or [], custom_items)
    else:
        system_keys = SYSTEM_SIDEBAR_KEYS

    system_by_id = {item.id: item for item in system_items}
    system_group = SidebarGroupOut(
        id="system",
        title="Системные",
        children=[system_by_id[key] for key in system_keys],
    )

    custom_group = SidebarGroupOut(
        id="custom",
        title="Мои списки",
        children=custom_items,
    )

    return [system_group, custom_group]


@api.post("/sidebar/order", response=SidebarOrderOut)
def sidebar_order_update(request, payload: SidebarOrderIn):
    user = _require_api_user(request)

    system_keys = _order_system_keys(payload.system_keys)

    user_list_ids = set(
        UserList.objects.filter(user=user).values_list("id", flat=True)
    )
    valid_custom_keys = [
        key
        for key in payload.custom_keys
        if key.startswith("list_") and key.removeprefix("list_").isdigit()
        and int(key.removeprefix("list_")) in user_list_ids
    ]
    custom_keys = list(dict.fromkeys(valid_custom_keys))
    missing_ids = user_list_ids - {
        int(key.removeprefix("list_"))
        for key in custom_keys
    }
    if missing_ids:
        missing_lists = (
            UserList.objects.filter(user=user, id__in=missing_ids)
            .order_by("-updated_at", "id")
        )
        custom_keys.extend(f"list_{lst.id}" for lst in missing_lists)

    layout, _ = SidebarLayout.objects.update_or_create(
        user=user,
        defaults={"system_keys": system_keys, "custom_keys": custom_keys},
    )
    return SidebarOrderOut(system_keys=layout.system_keys, custom_keys=layout.custom_keys)


# ------------------------------------ #
#          USER LISTS CRUD             #
# ------------------------------------ #


@api.post("/lists", response={201: UserListOut})
def list_create(request, payload: UserListCreateIn):
    user = _require_api_user(request)

    name = payload.name.strip()
    if not name:
        raise HttpError(400, "Name cannot be empty")

    user_list = UserList.objects.create(user=user, name=name)
    return UserListOut(id=user_list.id, name=user_list.name)


@api.patch("/lists/{list_id}", response=UserListOut)
def list_update(request, list_id: int, payload: UserListUpdateIn):
    user = _require_api_user(request)

    user_list = UserList.objects.filter(id=list_id, user=user).first()
    if user_list is None:
        raise HttpError(404, "List not found")

    name = payload.name.strip()
    if not name:
        raise HttpError(400, "Name cannot be empty")

    user_list.name = name
    user_list.save(update_fields=["name", "updated_at"])
    return UserListOut(id=user_list.id, name=user_list.name)


@api.delete("/lists/{list_id}", response=UserListDeleteOut)
def list_delete(request, list_id: int):
    user = _require_api_user(request)

    user_list = UserList.objects.filter(id=list_id, user=user).first()
    if user_list is None:
        raise HttpError(404, "List not found")

    # Удаляем связи фильмов, сами фильмы остаются
    UserListMovie.objects.filter(user_list=user_list).delete()
    user_list.delete()

    return UserListDeleteOut(message="Список удален")


# ------------------------------------ #
#           TMDB SYNC QUEUE            #
# ------------------------------------ #


def _build_tmdb_sync_queue_item_out(item: "TMDBSyncQueueItem") -> TMDBSyncQueueItemOut:
    return TMDBSyncQueueItemOut(
        id=item.id,
        movie_id=item.movie_id,
        movie_slug=item.movie.slug if item.movie_id else "",
        movie_title=item.movie.title if item.movie_id else "",
        movie_original_title=item.movie.original_title or "" if item.movie_id else "",
        movie_year=item.movie.year if item.movie_id else None,
        movie_description=item.movie.description or "" if item.movie_id else "",
        movie_poster_url=item.movie.poster_url if item.movie_id else None,
        movie_has_tmdb=bool(item.movie.tmdb_id) if item.movie_id else False,
        snapshot_title=item.snapshot_title,
        snapshot_original_title=item.snapshot_original_title,
        snapshot_year=item.snapshot_year,
        state=item.state,
        queued_at=_datetime_to_iso(item.queued_at) or "",
        started_at=_datetime_to_iso(item.started_at),
        finished_at=_datetime_to_iso(item.finished_at),
        result_status=item.result_status,
        result_title=item.result_title,
        result_original_title=item.result_original_title,
        result_year=item.result_year,
        result_tmdb_id=item.result_tmdb_id,
        result_media_type=item.result_media_type,
        result_message=item.result_message,
        retry_count=item.retry_count,
    )


@api.get("/tmdb-sync/state", response=TMDBSyncQueueStateOut)
def tmdb_sync_state(request):
    _require_api_user(request)
    return TMDBSyncQueueService.get_state()


@api.post("/tmdb-sync/queue", response=TMDBSyncQueueEnqueueOut)
def tmdb_sync_enqueue(request):
    _require_api_user(request)
    return TMDBSyncQueueService.enqueue_unsynced()


@api.post("/tmdb-sync/resync", response=TMDBSyncQueueEnqueueOut)
def tmdb_sync_resync(request):
    _require_api_user(request)
    return TMDBSyncQueueService.enqueue_resync()


@api.delete("/tmdb-sync/queue", response=TMDBSyncQueueDeleteOut)
def tmdb_sync_delete_all(request):
    _require_api_user(request)
    deleted = TMDBSyncQueueService.remove_all()
    return TMDBSyncQueueDeleteOut(deleted=deleted)


@api.delete("/tmdb-sync/queue/synced", response=TMDBSyncQueueDeleteOut)
def tmdb_sync_delete_synced(request):
    _require_api_user(request)
    deleted = TMDBSyncQueueService.remove_synced()
    return TMDBSyncQueueDeleteOut(deleted=deleted)


@api.delete("/tmdb-sync/items/{item_id}", response=TMDBSyncQueueDeleteOut)
def tmdb_sync_delete_item(request, item_id: int):
    _require_api_user(request)
    try:
        item = TMDBSyncQueueService.remove_item(item_id)
    except ValueError as exc:
        raise HttpError(400, str(exc))
    if item is None:
        raise HttpError(404, "Queue item not found")
    return TMDBSyncQueueDeleteOut(deleted=1)


@api.post("/tmdb-sync/start", response=TMDBSyncQueueStateOut)
def tmdb_sync_start(request):
    _require_api_user(request)
    try:
        TMDBSyncQueueService.start()
    except TMDBSyncKeysMissingError as exc:
        raise HttpError(400, str(exc))
    return TMDBSyncQueueService.get_state()


@api.post("/tmdb-sync/stop", response=TMDBSyncQueueStateOut)
def tmdb_sync_stop(request):
    _require_api_user(request)
    TMDBSyncQueueService.stop()
    return TMDBSyncQueueService.get_state()


@api.get("/tmdb-sync/items", response=TMDBSyncQueueItemsOut)
def tmdb_sync_items(request, state: str | None = None, offset: int = 0, limit: int = 100):
    _require_api_user(request)

    qs = TMDBSyncQueueItem.objects.select_related("movie").order_by("queued_at", "id")
    if state:
        qs = qs.filter(state=state)

    limit = min(max(limit, 1), 500)
    offset = max(offset, 0)
    total = qs.count()
    items = list(qs[offset : offset + limit])
    return TMDBSyncQueueItemsOut(
        items=[_build_tmdb_sync_queue_item_out(item) for item in items],
        total=total,
    )


class WritebackResultOut(Schema):
    success: bool
    action: str
    tmdb_id: int | None = None
    media_type: str | None = None
    error: str | None = None
    retry_after: int | None = None


class WritebackStatusOut(Schema):
    writeback_enabled: bool
    lists_writeback_enabled: bool
    write_token_present: bool
    total_user_movies: int
    total_with_tmdb: int
    total_without_tmdb: int
    # Error Log dash — дополнительные поля для дашборда
    skip_list_id: int | None = None
    lists_initialized: bool = False
    queue_pending: int = 0
    queue_error: int = 0
    queue_total: int = 0
    huey_pending: int | None = None  # ephemeral HUEY tasks, 2с окно


class WritebackSettingsIn(Schema):
    writeback_enabled: bool | None = None
    lists_writeback_enabled: bool | None = None


class WritebackSettingsOut(Schema):
    writeback_enabled: bool
    lists_writeback_enabled: bool


@api.post("/movies/{slug}/tmdb-writeback", response=list[WritebackResultOut])
def movie_tmdb_writeback(request, slug: str):
    """Принудительно синхронизировать фильм с TMDB (write-back)."""
    movie = Movie.objects.filter(slug=slug).first()
    if movie is None:
        raise HttpError(404, "Movie not found")
    user = _require_api_user(request)
    um = UserMovie.objects.filter(user=user, movie=movie).first()
    if um is None:
        raise HttpError(404, "No user movie data")
    from vault.services.tmdb_writeback_service import TmdbWritebackService

    results = TmdbWritebackService.sync_user_movie_to_tmdb(um)
    return [
        WritebackResultOut(
            success=r.success,
            action=r.action,
            tmdb_id=r.tmdb_id,
            media_type=r.media_type,
            error=r.error,
            retry_after=r.retry_after,
        )
        for r in results
    ]


@api.get("/tmdb-writeback/status", response=WritebackStatusOut)
def tmdb_writeback_status(request):
    _require_api_user(request)
    from moviefilter.models import UserPreferences

    prefs = UserPreferences.get()
    user = _resolve_api_user(request)
    total = UserMovie.objects.filter(user=user).count() if user else 0
    total_with = (
        UserMovie.objects.filter(user=user, movie__tmdb_id__isnull=False).count()
        if user
        else 0
    )
    # queue counters for dashboard
    from vault.models import TMDBWritebackQueueItem

    qs = TMDBWritebackQueueItem.objects.all()
    # single-user: filter by user if present, else global
    if user:
        # TMDBWritebackQueueItem.user is nullable legacy — count all + pending/error split
        pass
    queue_pending = qs.filter(state=TMDBWritebackQueueItem.State.PENDING).count()
    queue_error = qs.filter(state=TMDBWritebackQueueItem.State.ERROR).count()
    queue_total = queue_pending + queue_error

    # ephemeral HUEY pending — best-effort, SqliteHuey stores schedule in file
    huey_pending = None
    try:
        from movie_filter_pro.huey import HUEY as _HUEY

        # SqliteHuey: scheduled() returns scheduled tasks; pending() — ready queue
        # Both may raise if storage locked — swallow.
        scheduled = 0
        pending = 0
        try:
            # huey 2.x: HUEY.pending() / HUEY.scheduled() return Result iter
            if hasattr(_HUEY, "scheduled"):
                scheduled = len(list(_HUEY.scheduled()))
            if hasattr(_HUEY, "pending"):
                pending = len(list(_HUEY.pending()))
            # fallback: in-mem dispatch pending (WEB process only)
            try:
                from vault.services.tmdb_writeback_dispatch import TmdbWritebackDispatch

                dispatch_pending = len(getattr(TmdbWritebackDispatch, "_pending", {}))
                # huey file count + dispatch in-mem
                huey_pending = scheduled + pending + dispatch_pending
                # but if file counts are 0, keep dispatch count as at least
                if huey_pending == 0 and dispatch_pending:
                    huey_pending = dispatch_pending
            except Exception:
                huey_pending = scheduled + pending if (scheduled + pending) else None
        except Exception:
            huey_pending = None
    except Exception:
        huey_pending = None

    return WritebackStatusOut(
        writeback_enabled=bool(prefs.tmdb_writeback_enabled),
        lists_writeback_enabled=bool(prefs.tmdb_writeback_lists_enabled),
        write_token_present=bool(prefs.tmdb_v4_authenticated_access_token),
        total_user_movies=total,
        total_with_tmdb=total_with,
        total_without_tmdb=total - total_with,
        skip_list_id=getattr(prefs, "tmdb_skip_list_id", None),
        lists_initialized=bool(getattr(prefs, "tmdb_lists_initialized", False)),
        queue_pending=queue_pending,
        queue_error=queue_error,
        queue_total=queue_total,
        huey_pending=huey_pending,
    )


class WritebackQueueItemOut(Schema):
    id: int
    movie_id: int
    movie_title: str
    movie_slug: str
    state: str
    last_error: str
    attempts: int
    next_retry_at: str | None = None
    created_at: str


class WritebackQueueOut(Schema):
    items: list[WritebackQueueItemOut]
    total: int


def _build_writeback_queue_out(item) -> WritebackQueueItemOut:
    movie = getattr(item, "movie", None)
    return WritebackQueueItemOut(
        id=item.id,
        movie_id=item.movie_id,
        movie_title=movie.title if movie else f"#{item.movie_id}",
        movie_slug=movie.slug if movie else "",
        state=item.state,
        last_error=item.last_error or "",
        attempts=item.attempts,
        next_retry_at=_datetime_to_iso(item.next_retry_at),
        created_at=_datetime_to_iso(item.created_at) or "",
    )


@api.patch("/tmdb-writeback/settings", response=WritebackSettingsOut)
def tmdb_writeback_settings(request, payload: WritebackSettingsIn):
    _require_api_user(request)
    from moviefilter.models import UserPreferences

    prefs = UserPreferences.get()
    if payload.writeback_enabled is not None:
        prefs.tmdb_writeback_enabled = bool(payload.writeback_enabled)
        # single toggle: keep lists in sync with main (unless explicitly overridden)
        if payload.lists_writeback_enabled is None:
            prefs.tmdb_writeback_lists_enabled = bool(payload.writeback_enabled)
    if payload.lists_writeback_enabled is not None:
        prefs.tmdb_writeback_lists_enabled = bool(payload.lists_writeback_enabled)
    prefs.save(update_fields=["tmdb_writeback_enabled", "tmdb_writeback_lists_enabled"])
    return WritebackSettingsOut(
        writeback_enabled=bool(prefs.tmdb_writeback_enabled),
        lists_writeback_enabled=bool(prefs.tmdb_writeback_lists_enabled),
    )


@api.get("/tmdb-writeback/queue", response=WritebackQueueOut)
def tmdb_writeback_queue_list(request):
    _require_api_user(request)
    from vault.models import TMDBWritebackQueueItem

    qs = TMDBWritebackQueueItem.objects.select_related("movie").order_by("-created_at")
    items = list(qs[:200])
    return WritebackQueueOut(items=[_build_writeback_queue_out(i) for i in items], total=qs.count())


@api.delete("/tmdb-writeback/queue/{item_id}", response=dict)
def tmdb_writeback_queue_delete(request, item_id: int):
    _require_api_user(request)
    from vault.models import TMDBWritebackQueueItem

    deleted, _ = TMDBWritebackQueueItem.objects.filter(id=item_id).delete()
    if not deleted:
        raise HttpError(404, "Queue item not found")
    return {"deleted": deleted}


class WritebackRecentItemOut(Schema):
    movie_id: int
    movie_title: str
    movie_slug: str
    tmdb_id: int | None = None
    tmdb_media_type: str | None = None
    year: int | None = None
    watch_status: int | None = None
    watch_status_display: str | None = None
    is_favorite: bool = False
    rating: int | None = None
    updated_at: str | None = None
    writeback_status: str  # synced|pending|error|disabled|no_tmdb_id
    writeback_last_error: str | None = None
    writeback_next_retry_at: str | None = None
    writeback_reason: str | None = None


class WritebackRecentOut(Schema):
    items: list[WritebackRecentItemOut]
    total: int


@api.get("/tmdb-writeback/recent", response=WritebackRecentOut)
def tmdb_writeback_recent(request, limit: int = 20):
    """Последние UserMovie с tmdb-диагностикой для Error Log дашборда (вариант C)."""
    _require_api_user(request)
    user = _resolve_api_user(request)
    if user is None:
        return WritebackRecentOut(items=[], total=0)
    bounded = max(1, min(limit, 50))
    qs = (
        UserMovie.objects.filter(user=user)
        .select_related("movie")
        .order_by("-updated_at", "-id")
    )
    total = qs.count()
    items = list(qs[:bounded])
    # preload queue map: movie_id -> queue item for fast badge
    from vault.models import TMDBWritebackQueueItem

    queue_map = {
        q.movie_id: q
        for q in TMDBWritebackQueueItem.objects.filter(movie_id__in=[i.movie_id for i in items])
    }
    # prefs once for _should_writeback reason
    from vault.services.tmdb_writeback_service import TmdbWritebackService

    out: list[WritebackRecentItemOut] = []
    for um in items:
        movie = um.movie
        # writeback status per movie (queue > guard)
        qi = queue_map.get(movie.id)
        if qi:
            wb_status = qi.state
            wb_err = qi.last_error
            wb_next = _datetime_to_iso(qi.next_retry_at)
            wb_reason = None
        else:
            data = TmdbWritebackService.get_writeback_status(movie)
            wb_status = data.get("status", "unknown")
            wb_err = data.get("last_error")
            wb_next = data.get("next_retry_at")
            wb_reason = data.get("reason")
        # watch_status display
        try:
            ws_display = um.get_watch_status_display() if um.watch_status else None
        except Exception:
            ws_display = None
        out.append(
            WritebackRecentItemOut(
                movie_id=movie.id,
                movie_title=movie.title,
                movie_slug=movie.slug,
                tmdb_id=movie.tmdb_id,
                tmdb_media_type=movie.tmdb_media_type,
                year=movie.year,
                watch_status=um.watch_status,
                watch_status_display=ws_display,
                is_favorite=bool(um.is_favorite),
                rating=um.rating,
                updated_at=_datetime_to_iso(um.updated_at),
                writeback_status=wb_status,
                writeback_last_error=wb_err,
                writeback_next_retry_at=wb_next,
                writeback_reason=wb_reason,
            )
        )
    return WritebackRecentOut(items=out, total=total)


@api.post("/tmdb-writeback/queue/{item_id}/retry", response=WritebackQueueItemOut)
def tmdb_writeback_queue_retry(request, item_id: int):
    _require_api_user(request)
    from vault.models import TMDBWritebackQueueItem, UserMovie

    item = TMDBWritebackQueueItem.objects.select_related("movie").filter(id=item_id).first()
    if not item:
        raise HttpError(404, "Queue item not found")
    um = UserMovie.objects.filter(movie=item.movie).first()
    if not um:
        raise HttpError(404, "UserMovie not found for queued movie")
    from vault.services.tmdb_writeback_service import TmdbWritebackService

    TmdbWritebackService.sync_user_movie_to_tmdb(um)
    # reload item (может быть удалён при success)
    fresh = TMDBWritebackQueueItem.objects.filter(id=item_id).first()
    if fresh:
        return _build_writeback_queue_out(fresh)
    # success — возвращаем старую запись как удалённую (но клиент поймёт что очищено)
    return _build_writeback_queue_out(item)


# --- TMDB Auth (Svelte) ---

class TmdbAuthStatusOut(Schema):
    api_key_present: bool
    api_key_preview: str | None = None
    read_token_present: bool
    read_token_preview: str | None = None
    write_token_present: bool
    write_token_preview: str | None = None


class TmdbAuthStartOut(Schema):
    approve_url: str
    request_token: str


class TmdbAuthApproveOut(Schema):
    success: bool
    write_token: str | None = None
    message: str | None = None


def _preview_token(token: str | None, keep: int = 8) -> str | None:
    if not token:
        return None
    t = str(token).strip()
    if len(t) <= keep * 2:
        return t[:4] + "…" + t[-4:]
    return t[:keep] + "…" + t[-keep:]


@api.get("/tmdb-auth/status", response=TmdbAuthStatusOut)
def tmdb_auth_status(request):
    _require_api_user(request)
    from moviefilter.models import UserPreferences

    prefs = UserPreferences.get()
    return TmdbAuthStatusOut(
        api_key_present=bool(prefs.tmdb_api_key),
        api_key_preview=_preview_token(prefs.tmdb_api_key, 6),
        read_token_present=bool(prefs.tmdb_v4_read_access_token),
        read_token_preview=_preview_token(prefs.tmdb_v4_read_access_token),
        write_token_present=bool(prefs.tmdb_v4_authenticated_access_token),
        write_token_preview=_preview_token(prefs.tmdb_v4_authenticated_access_token),
    )


@api.post("/tmdb-auth/start", response=TmdbAuthStartOut)
def tmdb_auth_start(request):
    _require_api_user(request)
    from moviefilter.models import UserPreferences
    import requests as req_lib

    prefs = UserPreferences.get()
    if not prefs.tmdb_v4_read_access_token:
        raise HttpError(400, "Сначала заполни TMDB v4 read access token в Preferences")
    headers = {
        "Authorization": f"Bearer {prefs.tmdb_v4_read_access_token}",
        "Content-Type": "application/json",
    }
    try:
        r = req_lib.post("https://api.themoviedb.org/4/auth/request_token", headers=headers, json={}, timeout=15)
        data = r.json()
    except Exception as exc:
        raise HttpError(502, f"TMDB request_token failed: {exc}")
    if "request_token" not in data:
        raise HttpError(400, f"TMDB error: {data}")

    request_token = data["request_token"]
    approve_url = f"https://www.themoviedb.org/auth/access?request_token={request_token}"
    return TmdbAuthStartOut(approve_url=approve_url, request_token=request_token)


class TmdbAuthApproveIn(Schema):
    request_token: str | None = None


@api.post("/tmdb-auth/approve", response=TmdbAuthApproveOut)
def tmdb_auth_approve(request, payload: TmdbAuthApproveIn):
    _require_api_user(request)
    from moviefilter.models import UserPreferences
    import requests as req_lib

    prefs = UserPreferences.get()
    if not prefs.tmdb_v4_read_access_token:
        raise HttpError(400, "Нет read access token")

    request_token = (payload.request_token or "").strip()
    if not request_token:
        raise HttpError(400, "Нет request_token — передай его из Start auth")

    headers = {
        "Authorization": f"Bearer {prefs.tmdb_v4_read_access_token}",
        "Content-Type": "application/json",
    }
    try:
        r = req_lib.post(
            "https://api.themoviedb.org/4/auth/access_token",
            json={"request_token": request_token},
            headers=headers,
            timeout=15,
        )
        data = r.json()
    except Exception as exc:
        raise HttpError(502, f"TMDB access_token failed: {exc}")

    if "access_token" not in data:
        raise HttpError(400, f"TMDB error: {data}")

    access_token = data["access_token"]
    prefs.tmdb_v4_authenticated_access_token = access_token
    prefs.save(update_fields=["tmdb_v4_authenticated_access_token"])
    # сбрасываем синглтон клиента (важно для write-back)
    try:
        import tmdb_adapter.client_singleton as cs

        cs._tmdb_instance = None
        cs._last_token = None
        cs._last_key = None
    except Exception:
        pass

    # инициализация/восстановление списков на TMDB (чистый Huey, без блокировки ответа)
    try:
        from moviefilter.models import UserPreferences as UP2

        p2 = UP2.get()
        if p2.tmdb_writeback_enabled and p2.tmdb_v4_authenticated_access_token:
            from vault.tasks import tmdb_lists_init

            tmdb_lists_init.schedule(delay=2)
    except Exception:
        pass

    return TmdbAuthApproveOut(success=True, write_token=access_token, message="Write token сохранён")


@api.post("/tmdb-auth/logout", response=dict)
def tmdb_auth_logout(request):
    _require_api_user(request)
    from moviefilter.models import UserPreferences

    prefs = UserPreferences.get()
    if prefs.tmdb_v4_authenticated_access_token:
        try:
            from tmdb_adapter.client_singleton import get_tmdb_client

            tmdb = get_tmdb_client()
            tmdb.logout()
        except Exception:
            pass
        try:
            import tmdb_adapter.client_singleton as cs

            cs._tmdb_instance = None
            cs._last_token = None
            cs._last_key = None
        except Exception:
            pass
    prefs.tmdb_v4_authenticated_access_token = None
    prefs.save(update_fields=["tmdb_v4_authenticated_access_token"])
    return {"success": True}


@api.post("/collections/{tmdb_id}/refresh", response=CollectionBriefOut)
def collection_refresh(request, tmdb_id: int):
    _require_api_user(request)
    coll = Collection.objects.filter(tmdb_id=tmdb_id).first()
    if coll is None:
        raise HttpError(404, "Collection not found")
    try:
        from vault.services.collection_service import CollectionService

        CollectionService._sync_parts_data(coll)
        coll.refresh_from_db()
    except Exception as exc:
        raise HttpError(400, str(exc))
    # Найти любой фильм этой коллекции для сериализации (нужен movie для _build_collection_out)
    movie = Movie.objects.filter(collection=coll).first()
    if movie is None:
        # fallback — собрать вручную
        parts_out: list[CollectionPartOut] = []
        for p in list(coll.parts_data or []):
            try:
                pid = int(p.get("tmdb_id"))
            except Exception:
                continue
            parts_out.append(
                CollectionPartOut(
                    tmdb_id=pid,
                    title=str(p.get("title") or "").strip() or f"TMDB {pid}",
                    original_title=str(p.get("original_title") or "").strip() or None,
                    year=p.get("year"),
                    poster_url=_tmdb_image_url(p.get("poster_path"), size="w342") if p.get("poster_path") else None,
                    in_vault=False,
                    vault_slug=None,
                )
            )
        return CollectionBriefOut(
            tmdb_id=coll.tmdb_id,
            name=coll.name,
            overview=coll.overview or None,
            poster_url=_tmdb_image_url(coll.poster_path, size="w342") if coll.poster_path else None,
            backdrop_url=_tmdb_image_url(coll.backdrop_path, size="w780") if coll.backdrop_path else None,
            parts=parts_out,
        )
    out = _build_collection_out(movie)
    if out is None:
        raise HttpError(400, "Failed to build collection")
    return out
