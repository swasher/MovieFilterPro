"""Ninja API для bestfilmsof.

Все endpoint-ы требуют авторизации. Тяжёлый синк уходит в Huey; API только
атомарно занимает синк (`SyncService.claim`) и отдаёт текущий статус.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from bestfilmsof.constants import (
    GENRES,
    WEIGHT_KEYS,
    WEIGHT_PRESETS,
    YEAR_MIN,
)
from bestfilmsof.models import BestfilmsSync
from bestfilmsof.scoring import parse_weights, resolve_preset
from bestfilmsof.services import read_service, status_service
from bestfilmsof.services.sync_service import SyncService, is_stale, sync_key

api = NinjaAPI(title="BestFilmsof API", version="1.0", urls_namespace="bestfilmsof-api")


def _require_api_user(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        raise HttpError(401, "Authentication required")
    return user


class GenreOut(Schema):
    slug: str
    label: str


class PresetOut(Schema):
    name: str
    weights: dict[str, int] | None = None


class FiltersOut(Schema):
    years: list[int]
    genres: list[GenreOut]
    presets: list[PresetOut]
    weight_keys: list[str]
    year_min: int
    year_max: int


class MovieOut(Schema):
    position: int
    score: float | None = None
    imdb_id: str
    tmdb_id: int
    title: str
    title_ru: str | None = None
    overview: str | None = None
    overview_ru: str | None = None
    poster_path: str | None = None
    release_date: str | None = None
    imdb_rating: float | None = None
    imdb_votes: int | None = None
    tomato_meter: int | None = None
    metascore: int | None = None
    gross: int | None = None
    gross_scope: str | None = None
    oscar_wins: int = 0
    oscar_nominations: int = 0
    best_picture: bool = False
    award_points: int = 0
    awards_wins: int | None = None
    awards_nominations: int | None = None
    other_awards: list[Any] = []
    in_collection: bool = False
    collection_slug: str | None = None
    watch_status: str | None = None
    in_favorites: bool = False
    rating: int | None = None


class MovieListOut(Schema):
    mode: str = "list"
    year: int
    genre: str
    total: int
    page: int
    limit: int
    movies: list[MovieOut]
    weights: dict[str, int] | None = None
    preset: str = "default"
    status_filter: str = "all"
    counts: dict[str, int] = {}
    state: str
    synced_at: str | None = None
    is_stale: bool = False
    error: str | None = None


class GenreYearOut(Schema):
    year: int
    count: int
    top_score: float | None = None
    top_imdb_id: str
    top_tmdb_id: int
    top_title: str
    top_title_ru: str | None = None
    top_overview_ru: str | None = None
    top_poster_path: str | None = None
    top_release_date: str | None = None
    in_collection: bool = False
    collection_slug: str | None = None


class GenreSummaryOut(Schema):
    mode: str = "summary"
    genre: str
    total: int
    years: list[GenreYearOut]
    state: str
    synced_at: str | None = None
    is_stale: bool = False
    error: str | None = None


class SyncStateOut(Schema):
    key: str
    state: str
    synced_at: str | None = None
    started_at: str | None = None
    worker_started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    stats: dict[str, Any] | None = None


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _state(row: BestfilmsSync | None) -> str:
    if row is None:
        return "idle"
    if row.status == BestfilmsSync.Status.RUNNING:
        # Задача поставлена в очередь, но воркер ещё не начал её выполнять.
        return "syncing" if row.worker_started_at else "queued"
    if row.status == BestfilmsSync.Status.ERROR:
        return "error"
    if row.synced_at:
        return "ready"
    return "idle"


def _sync_state(row: BestfilmsSync | None) -> SyncStateOut:
    return SyncStateOut(
        key=row.key if row else "",
        state=_state(row),
        synced_at=_iso(row.synced_at) if row else None,
        started_at=_iso(row.started_at) if row else None,
        worker_started_at=_iso(row.worker_started_at) if row else None,
        finished_at=_iso(row.finished_at) if row else None,
        error=(row.error_message or None) if row else None,
        stats=(row.last_stats or None) if row else None,
    )


def _ensure_sync(year: int | None, genre: str, *, force: bool = False) -> BestfilmsSync:
    claimed, row, token = SyncService.claim(year, genre, force=force)
    if claimed:
        try:
            # Импорт внутри функции: tasks импортирует HUEY, а HUEY импортирует app.
            from bestfilmsof.tasks import bestfilmsof_sync

            bestfilmsof_sync(year, genre, token)
        except Exception as exc:
            # Постановка в очередь не удалась — не оставляем «вечный running».
            BestfilmsSync.objects.filter(pk=row.pk, run_token=token).update(
                status=BestfilmsSync.Status.ERROR,
                finished_at=timezone.now(),
                error_message=f"failed to enqueue sync task: {exc}"[:2000],
            )
            row.refresh_from_db()
    return row


def _validate_year(year: int) -> int:
    current_year = timezone.now().year
    if year < YEAR_MIN or year > current_year:
        raise HttpError(400, f"year must be {YEAR_MIN}..{current_year}")
    return year


def _validate_genre(genre: str | None) -> str:
    norm = (genre or "").lower()
    if norm and norm not in GENRES:
        raise HttpError(400, f"unknown genre: {genre!r}")
    return norm


def _bounded(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _weights_payload(
    preset: str,
    w_imdb: int,
    w_critics: int,
    w_awards: int,
    w_boxoffice: int,
) -> tuple[str, dict[str, int] | None]:
    preset, weights = resolve_preset(preset)
    if preset != "custom":
        return preset, weights
    weights = parse_weights(
        {
            "imdb": w_imdb,
            "critics": w_critics,
            "awards": w_awards,
            "boxoffice": w_boxoffice,
        }
    )
    if sum(weights.values()) <= 0:
        return "default", None
    return preset, weights


@api.get("/filters", response=FiltersOut)
def get_filters(request):
    _require_api_user(request)
    current_year = timezone.now().year
    return FiltersOut(
        years=list(range(current_year, YEAR_MIN - 1, -1)),
        genres=[
            GenreOut(slug=slug, label=slug.replace("-", " ").title())
            for slug in GENRES
        ],
        presets=[
            PresetOut(name=name, weights=weights)
            for name, weights in WEIGHT_PRESETS.items()
        ],
        weight_keys=list(WEIGHT_KEYS),
        year_min=YEAR_MIN,
        year_max=current_year,
    )


@api.get("/movies", response=MovieListOut)
def get_movies(
    request,
    year: int,
    genre: str = "",
    page: int = 1,
    limit: int = 500,
    preset: str = "default",
    status_filter: str = "all",
    w_imdb: int = 25,
    w_critics: int = 25,
    w_awards: int = 25,
    w_boxoffice: int = 25,
):
    user = _require_api_user(request)
    year = _validate_year(year)
    genre = _validate_genre(genre)
    page = max(1, page)
    limit = _bounded(limit, 1, 500)
    if status_filter not in status_service.STATUS_FILTERS:
        raise HttpError(400, f"unknown status filter: {status_filter!r}")
    preset, weights = _weights_payload(preset, w_imdb, w_critics, w_awards, w_boxoffice)

    row = _ensure_sync(year, genre)
    candidate_ids = read_service.get_pair_tmdb_ids(year, genre)
    status_map = status_service.get_status_map(user, candidate_ids)
    allowed_ids = status_service.filter_tmdb_ids(
        candidate_ids, status_map, status_filter
    )
    counts = status_service.count_by_status(candidate_ids, status_map)

    if weights:
        data = read_service.get_movies_weighted(
            year, genre, weights, page, limit, allowed_tmdb_ids=allowed_ids
        )
    else:
        data = read_service.get_movies(
            year, genre, page, limit, allowed_tmdb_ids=allowed_ids
        )
    status_service.apply_user_state(data["movies"], status_map)

    return MovieListOut(
        **data,
        year=year,
        genre=genre,
        weights=weights,
        preset=preset,
        status_filter=status_filter,
        counts=counts,
        state=_state(row),
        synced_at=_iso(row.synced_at) if row else None,
        is_stale=is_stale(year, genre, row.synced_at if row else None),
        error=(row.error_message or None) if row else None,
    )


@api.post("/movies/refresh", response=SyncStateOut)
def refresh_movies(
    request,
    year: int,
    genre: str = "",
):
    _require_api_user(request)
    year = _validate_year(year)
    genre = _validate_genre(genre)
    row = _ensure_sync(year, genre, force=True)
    return _sync_state(row)


@api.get("/genres/{genre}", response=GenreSummaryOut)
def get_genre_summary(request, genre: str):
    _require_api_user(request)
    norm = _validate_genre(genre)
    if not norm:
        raise HttpError(400, "genre is required")

    row = _ensure_sync(None, norm)
    data = read_service.get_genre_summary(norm)
    return GenreSummaryOut(
        **data,
        state=_state(row),
        synced_at=_iso(row.synced_at) if row else None,
        is_stale=is_stale(None, norm, row.synced_at if row else None),
        error=(row.error_message or None) if row else None,
    )


@api.post("/genres/{genre}/refresh", response=SyncStateOut)
def refresh_genre_summary(request, genre: str):
    _require_api_user(request)
    norm = _validate_genre(genre)
    if not norm:
        raise HttpError(400, "genre is required")
    row = _ensure_sync(None, norm, force=True)
    return _sync_state(row)


@api.get("/sync-state", response=SyncStateOut)
def get_sync_state(request, year: int | None = None, genre: str = ""):
    _require_api_user(request)
    norm = _validate_genre(genre)
    if year is not None:
        _validate_year(year)
    if year is None and not norm:
        raise HttpError(400, "year or genre is required")
    row = BestfilmsSync.objects.filter(key=sync_key(year, norm)).first()
    return _sync_state(row)
