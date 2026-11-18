"""
Сборка карточки фильма — вход для движка предсказания.

Карточка должна оставаться НЕЙТРАЛЬНОЙ: только факты из БД (жанры, страны, год,
рейтинги, описание, люди) и производные от них величины. Никаких «стоп-флагов»
и порогов: это зона профиля вкусов и системного промпта, а не кода.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from moviefilter.models import MovieRSS
from vault.models import Movie

DESCRIPTION_LIMIT = 900
YEAR_PATTERN = re.compile(r"\d{4}")


def _trim_text(text: str, limit: int) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rsplit(" ", 1)[0] + "…"


def _person_name(person) -> str:
    return (person.name or person.original_name or "").strip()


def build_movie_card(movie: Movie, now_year: int | None = None) -> dict[str, Any]:
    """Возвращает JSON-совместимую карточку фильма для промпта."""
    current_year = now_year or datetime.now().year

    genres = [genre.name.strip() for genre in movie.genres.all() if genre.name]
    countries = [country.name.strip() for country in movie.countries.all() if country.name]
    persons = list(movie.movie_persons.all())
    directors = [name for name in (_person_name(p.person) for p in persons if p.role == "director") if name][:3]
    actors = [name for name in (_person_name(p.person) for p in persons if p.role == "actor") if name][:6]

    card: dict[str, Any] = {
        "title": movie.title,
        "original_title": movie.original_title or None,
        "year": movie.year,
        "type": movie.get_movie_type_display(),
        "runtime_min": movie.duration,
        "genres": genres,
        "countries": countries,
        "language": (movie.tmdb_original_language or "").strip().lower() or None,
        "ratings": {
            "imdb": float(movie.imdb_rating) if movie.imdb_rating is not None else None,
            "imdb_votes": movie.imdb_votes,
            "tmdb": float(movie.tmdb_vote_average) if movie.tmdb_vote_average is not None else None,
        },
        "directors": directors,
        "cast": actors,
        "description": _trim_text(movie.description, DESCRIPTION_LIMIT),
        "age_years": (current_year - movie.year) if movie.year else None,
    }
    if movie.movie_type in (Movie.MovieType.SERIES, Movie.MovieType.MINISERIES):
        card["seasons"] = movie.seasons_count
        card["episodes"] = movie.episodes_count
    return card


def _split_list(raw: str | None, limit: int | None = None) -> list[str]:
    items = [item.strip() for item in (raw or "").split(",") if item.strip()]
    return items[:limit] if limit else items


def _year_value(raw: str | None) -> int | None:
    match = YEAR_PATTERN.search(raw or "")
    return int(match.group(0)) if match else None


def build_rss_movie_card(movie: MovieRSS, now_year: int | None = None) -> dict[str, Any]:
    """Карточка раздачи из ленты Kinozal — та же нейтральная схема, что и у Vault."""
    current_year = now_year or datetime.now().year
    year = _year_value(movie.year)

    return {
        "title": movie.title,
        "original_title": (movie.original_title or "").strip() or None,
        "year": year,
        "genres": _split_list(movie.genres, 10),
        "countries": _split_list(movie.countries),
        "ratings": {
            "imdb": float(movie.imdb_rating) if movie.imdb_rating is not None else None,
            "kinopoisk": float(movie.kinopoisk_rating) if movie.kinopoisk_rating is not None else None,
        },
        "directors": _split_list(movie.director, 3),
        "cast": _split_list(movie.actors, 6),
        "description": _trim_text(movie.plot, DESCRIPTION_LIMIT),
        "translation": (movie.translate or "").strip() or None,
        "age_years": (current_year - year) if year else None,
    }
