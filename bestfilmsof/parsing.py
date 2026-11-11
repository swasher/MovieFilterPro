"""Разбор ответов bestfilmsof.com в dict-структуры моделей."""

from __future__ import annotations

from datetime import date, datetime

# Поля BestfilmsEntry, которые сравниваются/обновляются при диффе.
ENTRY_FIELDS = [
    "tmdb_id",
    "position",
    "score",
    "title",
    "imdb_rating",
    "imdb_votes",
    "tomato_meter",
    "metascore",
    "gross",
    "gross_scope",
    "oscar_wins",
    "oscar_nominations",
    "best_picture",
    "award_points",
    "awards_wins",
    "awards_nominations",
    "other_awards",
    "comp_imdb",
    "comp_critics",
    "comp_awards",
    "comp_boxoffice",
    "fb_critics",
    "fb_boxoffice",
]


def to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_entry(raw: dict, position: int) -> dict | None:
    """Строка списка -> значения BestfilmsEntry (без year/genre/imdb_id)."""
    imdb_id = raw.get("imdb_id")
    meta = raw.get("metadata") or {}
    tmdb_id = to_int(meta.get("id"))
    if not imdb_id or not tmdb_id:
        return None
    return {
        "tmdb_id": tmdb_id,
        "position": position,
        "score": raw.get("weighted_score"),
        "title": raw.get("primary_title") or meta.get("title") or imdb_id,
        "imdb_rating": raw.get("average_rating"),
        "imdb_votes": to_int(raw.get("num_votes")),
        "tomato_meter": to_int(raw.get("tomato_meter")),
        "metascore": to_int(raw.get("metascore")),
        "gross": to_int(raw.get("gross")),
        "gross_scope": raw.get("gross_scope"),
        "oscar_wins": raw.get("oscar_wins") or 0,
        "oscar_nominations": raw.get("oscar_nominations") or 0,
        "best_picture": bool(raw.get("best_picture")),
        "award_points": raw.get("award_points") or 0,
        "awards_wins": to_int(raw.get("awards_wins")),
        "awards_nominations": to_int(raw.get("awards_nominations")),
        "other_awards": raw.get("other_awards") or [],
        "comp_imdb": raw.get("imdb_component"),
        "comp_critics": raw.get("critics_component"),
        "comp_awards": raw.get("awards_component"),
        "comp_boxoffice": raw.get("boxoffice_component"),
        "fb_critics": raw.get("critics_fallback"),
        "fb_boxoffice": raw.get("boxoffice_fallback"),
    }


def metadata_from_raw(raw: dict) -> dict | None:
    """Метаданные TMDB, которые bestfilmsof отдаёт бесплатно внутри ответа."""
    meta = raw.get("metadata") or {}
    tmdb_id = to_int(meta.get("id"))
    if not tmdb_id:
        return None
    title = meta.get("title") or raw.get("primary_title")
    if not title:
        return None
    return {
        "tmdb_id": tmdb_id,
        "title": title,
        "overview": meta.get("overview") or None,
        "poster_path": meta.get("poster_path") or None,
        "release_date": as_date(meta.get("release_date")),
    }
