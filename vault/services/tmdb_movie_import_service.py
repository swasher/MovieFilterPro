from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from django.db import transaction
from django.db.models import Q
from tmdbapis.exceptions import NotFound

from tmdb_adapter.client_singleton import get_tmdb_client
from vault.models import Movie
from vault.services.tmdb_movie_matching_service import TMDBCandidate
from vault.services.tmdb_movie_sync_service import TMDBMovieSyncService


ImportStatus = Literal["created", "exists"]
MediaType = Literal["movie", "tv"]


@dataclass(slots=True, frozen=True)
class TMDBMovieImportResult:
    status: ImportStatus
    message: str
    movie: Movie


class TMDBMovieImportService:
    SEARCH_RESULTS_PER_MEDIA = 10
    SEARCH_RESULTS_LIMIT = 10
    SEARCH_RESULTS_MAX_LIMIT = 20

    # ------------------------------------ #
    #          APPLICATION LAYER           #
    # ------------------------------------ #

    @classmethod
    def search_movies(cls, query: str, limit: int = SEARCH_RESULTS_LIMIT) -> tuple[TMDBCandidate, ...]:
        normalized_query = (query or "").strip()
        if len(normalized_query) < 2:
            return tuple()

        tmdb = get_tmdb_client()
        bounded_limit = max(1, min(limit, cls.SEARCH_RESULTS_MAX_LIMIT))
        candidates: dict[tuple[str, int], TMDBCandidate] = {}

        for media_type in ("movie", "tv"):
            items = cls._search_once(tmdb=tmdb, media_type=media_type, query=normalized_query)
            for item in items[: max(bounded_limit, cls.SEARCH_RESULTS_PER_MEDIA)]:
                candidate = cls._to_candidate(item=item, media_type=media_type)
                if candidate is None:
                    continue

                key = (candidate.media_type, candidate.tmdb_id)
                existing = candidates.get(key)
                if existing is None or cls._is_better_candidate(candidate, existing):
                    candidates[key] = candidate

        sorted_candidates = sorted(
            candidates.values(),
            key=lambda item: (
                -(item.popularity or 0.0),
                -(item.vote_average or 0.0),
                -(item.year or 0),
                item.title.lower(),
            ),
        )
        return tuple(sorted_candidates[:bounded_limit])

    @classmethod
    def lookup_by_id(cls, tmdb_id: int, media_type: str | None = None) -> TMDBCandidate | None:
        """Возвращает кандидата TMDB по id. Если media_type указан, ищет только в этом типе."""
        tmdb = get_tmdb_client()
        
        # Если media_type указан, используем его
        if media_type:
            normalized = cls._normalize_media_type(media_type)
            if normalized:
                details, resolved_media_type = cls._load_details(tmdb=tmdb, tmdb_id=tmdb_id, media_type=normalized)
                if details is None or resolved_media_type is None:
                    return None
                
                return TMDBCandidate(
                    tmdb_id=tmdb_id,
                    media_type=resolved_media_type,
                    title=cls._extract_title(details, resolved_media_type),
                    original_title=cls._extract_original_title(details, resolved_media_type) or "",
                    year=cls._extract_year(details, resolved_media_type),
                    score=0,
                    score_reasons=("manual_tmdb_id",),
                    poster_path=getattr(details, "poster_path", None),
                    popularity=cls._safe_float(getattr(details, "popularity", None)),
                    vote_average=cls._safe_float(getattr(details, "vote_average", None)),
                )
        
        # Если media_type не указан или не найден, пробуем movie, затем tv (старое поведение)
        details, resolved_media_type = cls._load_details(tmdb=tmdb, tmdb_id=tmdb_id, media_type="movie")
        if details is None or resolved_media_type is None:
            return None

        return TMDBCandidate(
            tmdb_id=tmdb_id,
            media_type=resolved_media_type,
            title=cls._extract_title(details, resolved_media_type),
            original_title=cls._extract_original_title(details, resolved_media_type) or "",
            year=cls._extract_year(details, resolved_media_type),
            score=0,
            score_reasons=("manual_tmdb_id",),
            poster_path=getattr(details, "poster_path", None),
            popularity=cls._safe_float(getattr(details, "popularity", None)),
            vote_average=cls._safe_float(getattr(details, "vote_average", None)),
        )

    @classmethod
    @transaction.atomic
    def import_movie(cls, tmdb_id: int, media_type: str) -> TMDBMovieImportResult:
        normalized_media_type = cls._normalize_media_type(media_type)
        if normalized_media_type is None:
            raise ValueError("Некорректный TMDB media_type")

        existing_movie = (
            Movie.objects.filter(tmdb_id=tmdb_id)
            .filter(Q(tmdb_media_type=normalized_media_type) | Q(tmdb_media_type__isnull=True) | Q(tmdb_media_type=""))
            .first()
        )
        if existing_movie is not None:
            return TMDBMovieImportResult(
                status="exists",
                message="Фильм уже есть в Vault",
                movie=existing_movie,
            )

        tmdb = get_tmdb_client()
        details, resolved_media_type = cls._load_details(tmdb=tmdb, tmdb_id=tmdb_id, media_type=normalized_media_type)
        if details is None or resolved_media_type is None:
            raise ValueError("Не удалось загрузить детали фильма из TMDB")

        movie = Movie.objects.create(
            title=cls._extract_title(details, resolved_media_type),
            original_title=cls._extract_original_title(details, resolved_media_type) or "",
            year=cls._extract_year(details, resolved_media_type),
            movie_type=cls._map_movie_type(resolved_media_type, details),
            status=Movie.Status.RELEASED,
            source=Movie.Source.TMDB,
            tmdb_id=tmdb_id,
            tmdb_media_type=resolved_media_type,
            poster=getattr(details, "poster_path", None),
            backdrop_path=getattr(details, "backdrop_path", None),
            tmdb_vote_average=cls._safe_float(getattr(details, "vote_average", None)),
            tmdb_vote_count=cls._safe_int(getattr(details, "vote_count", None)),
            tmdb_original_language=cls._extract_language_code(getattr(details, "original_language", None)),
        )

        candidate = TMDBCandidate(
            tmdb_id=tmdb_id,
            media_type=resolved_media_type,
            title=movie.title,
            original_title=movie.original_title or "",
            year=movie.year,
            score=0,
            score_reasons=("manual_import",),
            poster_path=movie.poster,
            popularity=cls._safe_float(getattr(details, "popularity", None)),
            vote_average=cls._safe_float(getattr(details, "vote_average", None)),
        )

        sync_result = TMDBMovieSyncService.sync_movie(
            movie=movie,
            force_rematch=True,
            selected_candidate=candidate,
        )
        if sync_result.status != "ok":
            raise ValueError(sync_result.message or "Не удалось импортировать фильм из TMDB")

        movie.refresh_from_db()
        return TMDBMovieImportResult(
            status="created",
            message="Фильм добавлен в Vault",
            movie=movie,
        )

    # ------------------------------------ #
    #            DOMAIN LAYER              #
    # ------------------------------------ #

    @classmethod
    def _search_once(cls, tmdb, media_type: MediaType, query: str):
        try:
            if media_type == "movie":
                response = tmdb.movie_search(query=query, include_adult=True)
            else:
                response = tmdb.tv_search(query=query, include_adult=True)
        except NotFound:
            return []
        except Exception:
            return []

        return response.results or []

    @classmethod
    def _to_candidate(cls, item, media_type: MediaType) -> TMDBCandidate | None:
        tmdb_id = cls._safe_int(getattr(item, "id", None))
        if not tmdb_id:
            return None

        title = cls._first_non_empty(getattr(item, "title", None), getattr(item, "name", None)) or ""
        original_title = cls._first_non_empty(
            getattr(item, "original_title", None),
            getattr(item, "original_name", None),
        ) or ""

        return TMDBCandidate(
            tmdb_id=tmdb_id,
            media_type=media_type,
            title=title,
            original_title=original_title,
            year=cls._extract_year(item, media_type),
            score=0,
            score_reasons=tuple(),
            poster_path=getattr(item, "poster_path", None),
            popularity=cls._safe_float(getattr(item, "popularity", None)),
            vote_average=cls._safe_float(getattr(item, "vote_average", None)),
        )

    @staticmethod
    def _is_better_candidate(left: TMDBCandidate, right: TMDBCandidate) -> bool:
        if (left.popularity or 0.0) != (right.popularity or 0.0):
            return (left.popularity or 0.0) > (right.popularity or 0.0)
        if (left.vote_average or 0.0) != (right.vote_average or 0.0):
            return (left.vote_average or 0.0) > (right.vote_average or 0.0)
        return (left.year or 0) > (right.year or 0)

    @classmethod
    def _load_details(cls, tmdb, tmdb_id: int, media_type: MediaType) -> tuple[object | None, MediaType | None]:
        try:
            if media_type == "movie":
                return tmdb.movie(tmdb_id), "movie"
            return tmdb.tv_show(tmdb_id), "tv"
        except Exception:
            fallback: MediaType = "tv" if media_type == "movie" else "movie"
            try:
                if fallback == "movie":
                    return tmdb.movie(tmdb_id), "movie"
                return tmdb.tv_show(tmdb_id), "tv"
            except Exception:
                return None, None

    @staticmethod
    def _normalize_media_type(value: str | None) -> MediaType | None:
        normalized = (value or "").strip().lower()
        if normalized in {"movie", "tv"}:
            return normalized
        return None

    @classmethod
    def _extract_title(cls, details, media_type: MediaType) -> str:
        value = cls._first_non_empty(
            getattr(details, "title", None) if media_type == "movie" else getattr(details, "name", None),
            getattr(details, "original_title", None) if media_type == "movie" else getattr(details, "original_name", None),
        )
        return (value or f"TMDB {media_type}").strip()

    @classmethod
    def _extract_original_title(cls, details, media_type: MediaType) -> str:
        value = (
            getattr(details, "original_title", None)
            if media_type == "movie"
            else getattr(details, "original_name", None)
        )
        return (value or "").strip()

    @classmethod
    def _extract_year(cls, item, media_type: MediaType) -> int | None:
        date_value = (
            getattr(item, "release_date", None)
            if media_type == "movie"
            else getattr(item, "first_air_date", None)
        )
        if isinstance(date_value, date):
            return date_value.year
        if hasattr(date_value, "year"):
            return cls._safe_int(getattr(date_value, "year", None))
        if isinstance(date_value, str) and len(date_value) >= 4:
            return cls._safe_int(date_value[:4])
        return None

    @staticmethod
    def _map_movie_type(media_type: MediaType, details=None) -> str:
        if media_type == "tv":
            if (getattr(details, "type", None) or "").strip().lower() == "miniseries":
                return Movie.MovieType.MINISERIES
            return Movie.MovieType.SERIES
        return Movie.MovieType.MOVIE

    @staticmethod
    def _first_non_empty(*values):
        for value in values:
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _safe_int(value) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_float(value) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _clean_text(value, max_len: int, default: str = "") -> str:
        text = (value or "").strip()
        if not text:
            return default
        return text[:max_len]

    @staticmethod
    def _extract_language_code(value) -> str | None:
        """Извлекает ISO-код языка из объекта tmdbapis.Language или строки."""
        if value is None:
            return None
        if hasattr(value, "iso_639_1"):
            return getattr(value, "iso_639_1", None)
        if hasattr(value, "code"):
            return getattr(value, "code", None)
        return str(value).strip() if str(value).strip() else None
