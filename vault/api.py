from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Exists, OuterRef, Q
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from vault.models import (
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
from vault.services.tmdb_sync_queue_service import TMDBSyncQueueService


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
    source: str
    source_display: str
    genres: list["NamedItemOut"]
    countries: list["NamedItemOut"]
    keywords: list[str] = []
    user_state: "UserStateOut"
    custom_lists: list["MovieUserListOut"]
    directors: list["PersonCreditOut"]
    actors: list["PersonCreditOut"]
    seasons: list["SeasonOut"] = []


class NamedItemOut(Schema):
    name: str
    slug: str | None = None


class PersonCreditOut(Schema):
    id: int
    name: str
    photo_url: str | None = None
    character_name: str | None = None
    is_favorite: bool = False


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


class TMDBSyncQueueStateIn(Schema):
    delay_seconds: int


class TMDBSyncQueueStateOut(Schema):
    enabled: bool
    delay_seconds: int
    counters: dict[str, int]  # pending, in_progress, synced, confirm, not_found, error
    total_unsynced: int  # сколько в базе вообще несинхронизированных (source=KINORIUM, tmdb_id IS NULL)


class TMDBSyncQueueItemOut(Schema):
    id: int
    movie_id: int
    movie_slug: str
    movie_title: str
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


@api.get("/movies", response=list[MovieOut])
def list_movies(
    request,
    limit: int = 50,
    offset: int = 0,
    genre: str | None = None,
    status: str | None = None,
    list: int | None = None,
    q: str | None = None,
    search_plot: bool = True,
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
    movie = Movie.objects.filter(slug=slug).first()
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
                photo_url=item.person.photo_url,
                is_favorite=item.person.id in favorite_person_ids,
            )
            for item in movie.get_directors().select_related("person")
        ],
        actors=[
            PersonCreditOut(
                id=item.person.id,
                name=item.person.name,
                photo_url=item.person.photo_url,
                character_name=item.character_name or None,
                is_favorite=item.person.id in favorite_person_ids,
            )
            for item in movie.get_actors().select_related("person")[:12]
        ],
        seasons=[
            _build_season_out(season, user=user)
            for season in movie.seasons.all().order_by("season_number")
        ],
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
        raise HttpError(400, str(exc))

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
        raise HttpError(400, str(exc))

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


SYSTEM_SIDEBAR_KEYS = ["watched", "will_watch", "wont_watch", "favorites"]

SYSTEM_SIDEBAR_ITEMS = [
    SidebarItemOut(id="watched", title="Просмотрено", href="/?status=watched", count=0),
    SidebarItemOut(id="will_watch", title="Буду смотреть", href="/?status=will_watch", count=0),
    SidebarItemOut(id="wont_watch", title="Не буду смотреть", href="/?status=wont_watch", count=0),
    SidebarItemOut(id="favorites", title="Избранное", href="/?status=favorites", count=0),
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
    TMDBSyncQueueService.start()
    return TMDBSyncQueueService.get_state()


@api.post("/tmdb-sync/stop", response=TMDBSyncQueueStateOut)
def tmdb_sync_stop(request):
    _require_api_user(request)
    TMDBSyncQueueService.stop()
    return TMDBSyncQueueService.get_state()


@api.patch("/tmdb-sync/state", response=TMDBSyncQueueStateOut)
def tmdb_sync_update_state(request, payload: TMDBSyncQueueStateIn):
    _require_api_user(request)
    try:
        TMDBSyncQueueService.set_delay(payload.delay_seconds)
    except ValueError as exc:
        raise HttpError(400, str(exc))
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
