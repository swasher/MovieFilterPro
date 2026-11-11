"""Чтение метаданных из коллекции Vault (только чтение).

Связь bestfilmsof с Vault логическая, по `tmdb_id`; FK нет.
Коллекция — приоритетный источник названия/описания/постера (там уже есть
русские данные после TMDB-синка).
"""

from __future__ import annotations

from django.db.models import Q

MOVIE_METADATA_FIELDS = (
    "tmdb_id",
    "tmdb_media_type",
    "title",
    "title_en",
    "original_title",
    "description",
    "poster",
    "release_date",
    "slug",
)


def get_collection_metadata(tmdb_ids) -> dict[int, dict]:
    """tmdb_id -> метаданные коллекции Vault.

    Учитываем только фильмы (`tmdb_media_type="movie"`), а также старые
    строки без media_type. Если на один tmdb_id внезапно нашлись и фильм,
    и строка без типа — приоритет у явного `movie`.
    """
    from vault.models import Movie

    ids = sorted({int(tmdb_id) for tmdb_id in tmdb_ids if tmdb_id})
    if not ids:
        return {}

    rows = (
        Movie.objects.filter(tmdb_id__in=ids)
        .filter(
            Q(tmdb_media_type=Movie.TMDBMediaType.MOVIE)
            | Q(tmdb_media_type__isnull=True)
            | Q(tmdb_media_type="")
        )
        .only(*MOVIE_METADATA_FIELDS)
    )

    result: dict[int, dict] = {}
    for movie in rows:
        is_movie = movie.tmdb_media_type == Movie.TMDBMediaType.MOVIE
        if movie.tmdb_id in result and not is_movie:
            continue
        result[movie.tmdb_id] = {
            "in_collection": True,
            "collection_slug": movie.slug or None,
            "title": movie.title_en or movie.original_title or movie.title,
            "title_ru": movie.title or None,
            "overview": None,
            "overview_ru": movie.description or None,
            "poster_path": movie.poster or None,
            "release_date": (
                movie.release_date.isoformat() if movie.release_date else None
            ),
        }
    return result
