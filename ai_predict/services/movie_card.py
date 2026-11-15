"""
Сборка карточки фильма — вход для движка предсказания.

Карточка должна оставаться НЕЙТРАЛЬНОЙ: только факты из БД (жанры, страны, год,
рейтинги, описание, люди) и производные от них величины. Никаких «стоп-флагов»
и порогов: это зона профиля вкусов и системного промпта, а не кода.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from vault.models import Movie

DESCRIPTION_LIMIT = 900


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
