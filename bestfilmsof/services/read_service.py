"""Чтение списков bestfilmsof из своей БД (без внешних запросов).

Приоритет метаданных при показе: коллекция Vault -> кеш bestfilmsof -> entry.
"""

from __future__ import annotations

from bestfilmsof.models import (
    BestfilmsCache,
    BestfilmsEntry,
    BestfilmsGenreYear,
)
from bestfilmsof.scoring import rescore
from bestfilmsof.services.collection_service import get_collection_metadata


def norm_genre(genre: str | None) -> str:
    """None -> "" («весь год»). Ключ для entry/sync-таблиц."""
    return (genre or "").lower()


def _cache_payload(cache: BestfilmsCache | None) -> dict:
    if cache is None:
        return {}
    return {
        "title": cache.title,
        "overview": cache.overview,
        "title_ru": cache.title_ru,
        "overview_ru": cache.overview_ru,
        "poster_path": cache.poster_path,
        "release_date": (
            cache.release_date.isoformat() if cache.release_date else None
        ),
    }


def _movie_payload(
    entry: BestfilmsEntry,
    cache: BestfilmsCache | None,
    collection: dict | None,
    *,
    position: int | None = None,
    score: float | None = None,
) -> dict:
    data = {
        "position": entry.position if position is None else position,
        "score": entry.score if score is None else score,
        "imdb_id": entry.imdb_id,
        "tmdb_id": entry.tmdb_id,
        "title": entry.title,
        "title_ru": None,
        "overview": None,
        "overview_ru": None,
        "poster_path": None,
        "release_date": None,
        "imdb_rating": entry.imdb_rating,
        "imdb_votes": entry.imdb_votes,
        "tomato_meter": entry.tomato_meter,
        "metascore": entry.metascore,
        "gross": entry.gross,
        "gross_scope": entry.gross_scope,
        "oscar_wins": entry.oscar_wins,
        "oscar_nominations": entry.oscar_nominations,
        "best_picture": entry.best_picture,
        "award_points": entry.award_points,
        "awards_wins": entry.awards_wins,
        "awards_nominations": entry.awards_nominations,
        "other_awards": entry.other_awards or [],
        "in_collection": False,
        "collection_slug": None,
        "watch_status": None,
        "in_favorites": False,
        "rating": None,
    }
    data.update(_cache_payload(cache))
    if collection:
        # Коллекция Vault — приоритетный источник. Пустые значения не затирают
        # английский fallback из кеша bestfilmsof.
        for key, value in collection.items():
            if value is not None and value != "":
                data[key] = value
    return data


def _collection_map(entries) -> dict[int, dict]:
    return get_collection_metadata(entry.tmdb_id for entry in entries)


def get_pair_tmdb_ids(year: int, genre: str | None = None) -> list[int]:
    """Все tmdb_id выбранной пары (для фильтрации по статусам)."""
    return list(
        BestfilmsEntry.objects.filter(year=year, genre=norm_genre(genre)).values_list(
            "tmdb_id", flat=True
        )
    )


def get_movies(
    year: int,
    genre: str | None = None,
    page: int = 1,
    limit: int = 20,
    allowed_tmdb_ids: set[int] | None = None,
) -> dict:
    """Произвольная пагинация уже сохранённого слепка."""
    page = max(1, page)
    limit = max(1, limit)
    norm = norm_genre(genre)
    queryset = BestfilmsEntry.objects.filter(year=year, genre=norm).order_by("position")
    if allowed_tmdb_ids is not None:
        queryset = queryset.filter(tmdb_id__in=allowed_tmdb_ids)
    total = queryset.count()
    entries = list(queryset[(page - 1) * limit : page * limit])
    caches = BestfilmsCache.objects.in_bulk(entry.tmdb_id for entry in entries)
    collections = _collection_map(entries)
    movies = [
        _movie_payload(entry, caches.get(entry.tmdb_id), collections.get(entry.tmdb_id))
        for entry in entries
    ]
    return {"total": total, "page": page, "limit": limit, "movies": movies}


def get_movies_weighted(
    year: int,
    genre: str | None,
    weights: dict[str, int],
    page: int = 1,
    limit: int = 20,
    allowed_tmdb_ids: set[int] | None = None,
) -> dict:
    """Тот же слепок, но position/score пересчитаны под свои веса."""
    page = max(1, page)
    limit = max(1, limit)
    norm = norm_genre(genre)
    queryset = BestfilmsEntry.objects.filter(year=year, genre=norm)
    if allowed_tmdb_ids is not None:
        queryset = queryset.filter(tmdb_id__in=allowed_tmdb_ids)
    ranked = []
    for entry in queryset:
        score = rescore(entry, weights)
        if score is not None:
            ranked.append((score, entry))
    ranked.sort(key=lambda item: (-item[0], item[1].position))
    total = len(ranked)
    chunk = ranked[(page - 1) * limit : page * limit]
    caches = BestfilmsCache.objects.in_bulk(entry.tmdb_id for _, entry in chunk)
    collections = _collection_map([entry for _, entry in chunk])
    movies = []
    for index, (score, entry) in enumerate(chunk, start=(page - 1) * limit + 1):
        movies.append(
            _movie_payload(
                entry,
                caches.get(entry.tmdb_id),
                collections.get(entry.tmdb_id),
                position=index,
                score=score,
            )
        )
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "movies": movies,
    }


def get_genre_summary(genre: str) -> dict:
    """Строки жанровой сводки от новых годов к старым."""
    norm = norm_genre(genre)
    rows = list(BestfilmsGenreYear.objects.filter(genre=norm).order_by("-year"))
    caches = BestfilmsCache.objects.in_bulk(row.top_tmdb_id for row in rows)
    collections = get_collection_metadata(row.top_tmdb_id for row in rows)

    years = []
    for row in rows:
        cache = caches.get(row.top_tmdb_id)
        collection = collections.get(row.top_tmdb_id)
        meta = _cache_payload(cache)
        if collection:
            for key, value in collection.items():
                if value is not None and value != "":
                    meta[key] = value
        years.append(
            {
                "year": row.year,
                "count": row.count,
                "top_score": row.top_score,
                "top_imdb_id": row.top_imdb_id,
                "top_tmdb_id": row.top_tmdb_id,
                "top_title": meta.get("title") or row.top_title,
                "top_title_ru": meta.get("title_ru"),
                "top_overview_ru": meta.get("overview_ru"),
                "top_poster_path": meta.get("poster_path"),
                "top_release_date": meta.get("release_date"),
                "in_collection": bool(collection),
                "collection_slug": (collection or {}).get("collection_slug"),
            }
        )
    return {"genre": norm, "total": len(years), "years": years}
