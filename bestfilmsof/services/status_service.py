"""Связь bestfilmsof с пользовательскими статусами Vault по `tmdb_id`."""

from __future__ import annotations

from django.db.models import Q

from vault.models import Movie, UserMovie
from vault.services.movie_status_service import MovieStatusService

STATUS_ALL = "all"
STATUS_UNWATCHED = "unwatched"
STATUS_WILL_WATCH = "will_watch"
STATUS_FILTERS = (STATUS_ALL, STATUS_UNWATCHED, STATUS_WILL_WATCH)


def get_status_map(user, tmdb_ids) -> dict[int, dict]:
    """tmdb_id -> статус пользователя (только чтение, без N+1)."""
    ids = {int(tmdb_id) for tmdb_id in tmdb_ids if tmdb_id}
    if user is None or not ids:
        return {}

    rows = (
        UserMovie.objects.filter(user=user, movie__tmdb_id__in=ids)
        .filter(
            Q(movie__tmdb_media_type=Movie.TMDBMediaType.MOVIE)
            | Q(movie__tmdb_media_type__isnull=True)
            | Q(movie__tmdb_media_type="")
        )
        .values(
            "movie__tmdb_id",
            "movie__tmdb_media_type",
            "watch_status",
            "is_favorite",
            "rating",
        )
    )

    result: dict[int, dict] = {}
    for row in rows:
        tmdb_id = row["movie__tmdb_id"]
        if tmdb_id is None:
            continue
        is_movie = row["movie__tmdb_media_type"] == Movie.TMDBMediaType.MOVIE
        if tmdb_id in result and not is_movie:
            continue
        result[tmdb_id] = {
            "watch_status": MovieStatusService.WATCH_STATUS_TO_STATUS_KEY.get(
                row["watch_status"]
            ),
            "in_favorites": bool(row["is_favorite"]),
            "rating": row["rating"],
        }
    return result


def count_by_status(tmdb_ids, status_map: dict[int, dict]) -> dict[str, int]:
    counts = {"all": len(tmdb_ids), "unwatched": 0, "will_watch": 0}
    for tmdb_id in tmdb_ids:
        watch_status = (status_map.get(tmdb_id) or {}).get("watch_status")
        if watch_status != "watched":
            counts["unwatched"] += 1
        if watch_status == "will_watch":
            counts["will_watch"] += 1
    return counts


def filter_tmdb_ids(tmdb_ids, status_map: dict[int, dict], status_filter: str):
    """None = без ограничений (все фильмы)."""
    if status_filter == STATUS_ALL:
        return None
    if status_filter == STATUS_UNWATCHED:
        return {
            tmdb_id
            for tmdb_id in tmdb_ids
            if (status_map.get(tmdb_id) or {}).get("watch_status") != "watched"
        }
    if status_filter == STATUS_WILL_WATCH:
        return {
            tmdb_id
            for tmdb_id in tmdb_ids
            if (status_map.get(tmdb_id) or {}).get("watch_status") == "will_watch"
        }
    raise ValueError(f"unknown status filter: {status_filter!r}")


def apply_user_state(movies: list[dict], status_map: dict[int, dict]) -> None:
    for movie in movies:
        state = status_map.get(movie["tmdb_id"]) or {}
        movie["watch_status"] = state.get("watch_status")
        movie["in_favorites"] = bool(state.get("in_favorites"))
        movie["rating"] = state.get("rating")
