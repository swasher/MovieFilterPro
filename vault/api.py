from django.contrib.auth.models import User
from django.db.models import Count
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from vault.models import Genre, Movie, UserList, UserMovie
from vault.services.movie_status_service import MovieStatusService
from vault.services.tmdb_movie_sync_service import TMDBMovieSyncService


class MovieOut(Schema):
    id: int
    title: str
    original_title: str | None = None
    year: int | None = None
    slug: str
    poster_url: str | None = None


class MovieDetailOut(Schema):
    id: int
    title: str
    original_title: str | None = None
    year: int | None = None
    slug: str
    description: str
    movie_type: str
    status: str
    imdb_rating: float | None = None
    poster_url: str | None = None


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


class TMDBSyncIn(Schema):
    force_rematch: bool = False


class TMDBSyncOut(Schema):
    status: str
    message: str
    updated_fields: list[str] = []
    orphan_persons_deleted: int = 0


api = NinjaAPI(title="Vault API", version="1.0")


def _resolve_api_user(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user
    return User.objects.order_by("id").first()


@api.get("/movies", response=list[MovieOut])
def list_movies(
    request,
    limit: int = 50,
    genre: str | None = None,
    status: str | None = None,
    list: int | None = None,
):
    user = _resolve_api_user(request)
    qs = (
        Movie.objects.filter(status=Movie.Status.RELEASED)
        .order_by("-year", "title")
    )
    if genre:
        qs = qs.filter(genres__slug=genre)
    if user and status:
        if status == "favorites":
            qs = qs.filter(user_movies__user=user, user_movies__is_favorite=True)
        elif status == "watched":
            qs = qs.filter(user_movies__user=user, user_movies__watch_status=UserMovie.WatchStatus.WATCHED)
        elif status == "will_watch":
            qs = qs.filter(user_movies__user=user, user_movies__watch_status=UserMovie.WatchStatus.PLAN)
        elif status == "wont_watch":
            qs = qs.filter(user_movies__user=user, user_movies__watch_status=UserMovie.WatchStatus.SKIP)
    if user and list:
        qs = qs.filter(in_lists__user_list_id=list, in_lists__user_list__user=user)

    qs = qs.distinct()[:limit]
    return [
        MovieOut(
            id=movie.id,
            title=movie.title,
            original_title=movie.original_title,
            year=movie.year,
            slug=movie.slug,
            poster_url=movie.poster_url,
        )
        for movie in qs
    ]


@api.get("/movies/{slug}", response=MovieDetailOut)
def movie_detail(request, slug: str):
    movie = Movie.objects.filter(slug=slug).first()
    if movie is None:
        raise HttpError(404, "Movie not found")
    imdb_rating = float(movie.imdb_rating) if movie.imdb_rating is not None else None

    return MovieDetailOut(
        id=movie.id,
        title=movie.title,
        original_title=movie.original_title,
        year=movie.year,
        slug=movie.slug,
        description=movie.description or "",
        movie_type=movie.movie_type,
        status=movie.status,
        imdb_rating=imdb_rating,
        poster_url=movie.poster_url,
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

    return TMDBSyncOut(
        status=result.status,
        message=result.message,
        updated_fields=list(result.updated_fields),
        orphan_persons_deleted=result.orphan_persons_deleted,
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

    genres_qs = (
        Genre.objects.filter(movies__status=Movie.Status.RELEASED)
        .annotate(movies_count=Count("movies"))
        .order_by("name")
    )
    genres_group = SidebarGroupOut(
        id="genres",
        title="Жанры",
        children=[
            SidebarItemOut(
                id=f"genre_{genre.slug}",
                title=genre.name,
                href=f"/?genre={genre.slug}",
                count=genre.movies_count,
            )
            for genre in genres_qs
        ],
    )

    return [system_group, custom_group, genres_group]
