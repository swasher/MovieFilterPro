from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Exists, OuterRef, Q
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from vault.models import Genre, Movie, MoviePerson, Person, UserList, UserListMovie, UserMovie, VaultConnectionEvent
from vault.services.movie_status_service import MovieStatusService
from vault.services.tmdb_movie_import_service import TMDBMovieImportService
from vault.services.tmdb_movie_matching_service import TMDBCandidate
from vault.services.tmdb_movie_sync_service import TMDBMovieSyncService


class MovieOut(Schema):
    id: int
    title: str
    original_title: str | None = None
    year: int | None = None
    slug: str
    poster_url: str | None = None
    movie_type: str | None = None
    in_watched: bool = False
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
    status: str
    status_display: str
    imdb_rating: float | None = None
    poster_url: str | None = None
    duration: int | None = None
    age_rating: str | None = None
    trailer_url: str | None = None
    tmdb_id: int | None = None
    tmdb_linked: bool
    source: str
    source_display: str
    genres: list["NamedItemOut"]
    countries: list["NamedItemOut"]
    user_state: "UserStateOut"
    custom_lists: list["MovieUserListOut"]
    directors: list["PersonCreditOut"]
    actors: list["PersonCreditOut"]


class NamedItemOut(Schema):
    name: str
    slug: str | None = None


class PersonCreditOut(Schema):
    id: int
    name: str
    photo_url: str | None = None
    character_name: str | None = None


class UserStateOut(Schema):
    in_watched: bool
    in_will_watch: bool
    in_wont_watch: bool
    in_favorites: bool
    rating: int | None = None
    note: str = ""


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


class PersonMovieOut(Schema):
    id: int
    title: str
    slug: str
    year: int | None = None
    poster_url: str | None = None
    role: str
    role_display: str
    character_name: str | None = None


class PersonDetailOut(Schema):
    id: int
    name: str
    original_name: str
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
        note=state["note"],
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
    in_favorites = False
    if user is not None:
        state = MovieStatusService.get_movie_status(user, movie)
        in_watched = state["in_watched"]
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
        in_favorites=in_favorites,
    )


@api.get("/movies", response=list[MovieOut])
def list_movies(
    request,
    limit: int = 50,
    genre: str | None = None,
    status: str | None = None,
    list: int | None = None,
    q: str | None = None,
    order: str = "-year",
    year_from: int | None = None,
    year_to: int | None = None,
    movie_type: str | None = None,
    is_favorite: bool | None = None,
    watch_status: str | None = None,
):
    user = _resolve_api_user(request)
    qs = Movie.objects.filter(status=Movie.Status.RELEASED)

    if genre:
        genre_slugs = [g.strip() for g in genre.split(",") if g.strip()]
        if genre_slugs:
            qs = qs.filter(genres__slug__in=genre_slugs).distinct()
    if q:
        query = q.strip()
        if query:
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(original_title__icontains=query)
                | Q(description__icontains=query)
            )
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
        "-year": ("-year", "title"),
        "year": ("year", "title"),
        "-imdb_rating": ("-imdb_rating", "title"),
        "imdb_rating": ("imdb_rating", "title"),
        "title": ("title",),
        "-title": ("-title",),
    }
    if order in {"-added_at", "added_at"}:
        if user and list:
            ordering = (
                ("-in_lists__added_at", "-year", "title")
                if order == "-added_at"
                else ("in_lists__added_at", "-year", "title")
            )
        elif user and status:
            ordering = (
                ("-user_movies__created_at", "-year", "title")
                if order == "-added_at"
                else ("user_movies__created_at", "-year", "title")
            )
        else:
            ordering = (
                ("-created_at", "-year", "title")
                if order == "-added_at"
                else ("created_at", "-year", "title")
            )
    else:
        ordering = allowed_orders.get(order, allowed_orders["-year"])

    qs = qs.order_by(*ordering).distinct()[:limit]
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

    return MovieDetailOut(
        id=movie.id,
        title=movie.title,
        original_title=movie.original_title,
        year=movie.year,
        slug=movie.slug,
        description=movie.description or "",
        movie_type=movie.movie_type,
        movie_type_display=movie.get_movie_type_display(),
        status=movie.status,
        status_display=movie.get_status_display(),
        imdb_rating=_decimal_to_float(movie.imdb_rating),
        poster_url=movie.poster_url,
        duration=movie.duration,
        age_rating=movie.age_rating or None,
        trailer_url=movie.trailer_url or None,
        tmdb_id=movie.tmdb_id,
        tmdb_linked=bool(movie.tmdb_id),
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
        user_state=_build_user_state(user, movie),
        custom_lists=_build_movie_user_lists(user, movie),
        directors=[
            PersonCreditOut(
                id=item.person.id,
                name=item.person.name,
                photo_url=item.person.photo_url,
            )
            for item in movie.get_directors().select_related("person")
        ],
        actors=[
            PersonCreditOut(
                id=item.person.id,
                name=item.person.name,
                photo_url=item.person.photo_url,
                character_name=item.character_name or None,
            )
            for item in movie.get_actors().select_related("person")[:12]
        ],
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

    filmography_qs = (
        MoviePerson.objects.filter(person=person)
        .select_related("movie")
        .order_by("-movie__year", "order", "id")
    )
    filmography = [
        PersonMovieOut(
            id=item.movie.id,
            title=item.movie.title,
            slug=item.movie.slug,
            year=item.movie.year,
            poster_url=item.movie.poster_url,
            role=item.role,
            role_display=item.get_role_display(),
            character_name=item.character_name or None,
        )
        for item in filmography_qs
    ]

    years = [item.movie.year for item in filmography_qs if item.movie.year is not None]

    return PersonDetailOut(
        id=person.id,
        name=person.name,
        original_name=person.original_name,
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
    )


@api.get("/sidebar", response=list[SidebarGroupOut])
def sidebar_data(request):
    user = _resolve_api_user(request)
    if user is None:
        return [
            SidebarGroupOut(
                id="system",
                title="Системные",
                children=[
                    SidebarItemOut(id="watched", title="Просмотрено", href="/?status=watched", count=0),
                    SidebarItemOut(id="will_watch", title="Буду смотреть", href="/?status=will_watch", count=0),
                    SidebarItemOut(id="wont_watch", title="Не буду смотреть", href="/?status=wont_watch", count=0),
                    SidebarItemOut(id="favorites", title="Избранное", href="/?status=favorites", count=0),
                ],
            ),
            SidebarGroupOut(id="custom", title="Мои списки", children=[]),
        ]

    counts = MovieStatusService.get_system_lists_counts(user)

    system_group = SidebarGroupOut(
        id="system",
        title="Системные",
        children=[
            SidebarItemOut(id="watched", title="Просмотрено", href="/?status=watched", count=counts["watched"]),
            SidebarItemOut(id="will_watch", title="Буду смотреть", href="/?status=will_watch", count=counts["will_watch"]),
            SidebarItemOut(id="wont_watch", title="Не буду смотреть", href="/?status=wont_watch", count=counts["wont_watch"]),
            SidebarItemOut(id="favorites", title="Избранное", href="/?status=favorites", count=counts["favorites"]),
        ],
    )

    custom_lists_qs = (
        UserList.objects.filter(user=user)
        .annotate(movies_count=Count("list_movies"))
        .order_by("-updated_at", "id")
    )
    custom_group = SidebarGroupOut(
        id="custom",
        title="Мои списки",
        children=[
            SidebarItemOut(
                id=f"list_{item.id}",
                title=item.name,
                href=f"/?list={item.id}",
                count=item.movies_count,
            )
            for item in custom_lists_qs
        ],
    )

    return [system_group, custom_group]


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
