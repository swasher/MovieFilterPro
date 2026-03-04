from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from django.db import transaction
from django.utils import timezone

from core.models import Country as CoreCountry
from tmdb_adapter.client_singleton import get_tmdb_client
from vault.models import Genre, Movie
from vault.services.tmdb_movie_matching_service import (
    TMDBCandidate,
    TMDBMovieMatchingService,
)


SyncStatus = Literal["ok", "needs_user_choice", "error"]
MediaType = Literal["movie", "tv"]


@dataclass(slots=True, frozen=True)
class TMDBSyncResult:
    status: SyncStatus
    message: str
    updated_fields: tuple[str, ...] = field(default_factory=tuple)
    selected_candidate: TMDBCandidate | None = None
    candidates: tuple[TMDBCandidate, ...] = field(default_factory=tuple)


class TMDBMovieSyncService:
    """Синхронизация локального vault.Movie с данными TMDB."""

    @classmethod
    @transaction.atomic
    def sync_movie(
        cls,
        movie: Movie,
        force_rematch: bool = False,
        selected_candidate: TMDBCandidate | None = None,
    ) -> TMDBSyncResult:
        tmdb = get_tmdb_client()

        candidate = selected_candidate
        if candidate is None:
            if movie.tmdb_id and movie.tmdb_media_type and not force_rematch:
                candidate = TMDBCandidate(
                    tmdb_id=movie.tmdb_id,
                    media_type=movie.tmdb_media_type,
                    title=movie.title or "",
                    original_title=movie.original_title or "",
                    year=movie.year,
                    score=0,
                    score_reasons=("stored_tmdb_id",),
                    poster_path=movie.poster,
                    popularity=None,
                    vote_average=None,
                )
            else:
                match_result = TMDBMovieMatchingService.match_movie(movie)
                if match_result.status == "needs_user_choice":
                    return TMDBSyncResult(
                        status="needs_user_choice",
                        message=match_result.message,
                        candidates=match_result.candidates,
                    )
                if match_result.status == "not_found" or match_result.selected_candidate is None:
                    return TMDBSyncResult(
                        status="error",
                        message=match_result.message or "Не удалось подобрать TMDB фильм",
                    )
                candidate = match_result.selected_candidate

        details, media_type = cls._load_details(tmdb, candidate)
        if details is None or media_type is None:
            return TMDBSyncResult(
                status="error",
                message="Не удалось загрузить детали фильма из TMDB",
            )

        updated_fields: list[str] = []
        set_field = cls._field_setter(movie, updated_fields)

        # Идентификация источника TMDB
        set_field("tmdb_id", candidate.tmdb_id)
        set_field("tmdb_media_type", media_type)
        set_field("tmdb_last_synced_at", timezone.now())
        set_field("source", Movie.Source.TMDB)

        # Общие поля
        if media_type == "movie":
            cls._apply_movie_payload(movie, details, set_field)
        else:
            cls._apply_tv_payload(movie, details, set_field)

        status_value = cls._map_tmdb_status(media_type, getattr(details, "status", None))
        if status_value:
            set_field("status", status_value)

        trailer_url = cls._extract_youtube_trailer_url(getattr(details, "videos", None))
        if trailer_url:
            set_field("trailer_url", trailer_url)

        if updated_fields:
            movie.save(update_fields=updated_fields)

        relations_updated: list[str] = []
        if cls._sync_genres(movie, getattr(details, "genres", None)):
            relations_updated.append("genres")
        if cls._sync_countries(
            movie,
            countries=getattr(details, "countries", None),
            origin_countries=getattr(details, "origin_countries", None),
        ):
            relations_updated.append("countries")

        return TMDBSyncResult(
            status="ok",
            message="Данные фильма обновлены из TMDB",
            updated_fields=tuple(updated_fields + relations_updated),
            selected_candidate=candidate,
        )

    @classmethod
    def _load_details(cls, tmdb, candidate: TMDBCandidate):
        media_type = candidate.media_type
        tmdb_id = candidate.tmdb_id

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
    def _field_setter(movie: Movie, updated_fields: list[str]):
        def _set(name: str, value):
            current = getattr(movie, name)
            if current != value:
                setattr(movie, name, value)
                if name not in updated_fields:
                    updated_fields.append(name)

        return _set

    @classmethod
    def _apply_movie_payload(cls, movie: Movie, details, set_field):
        release_date = getattr(details, "release_date", None)
        release_year = getattr(release_date, "year", None) if release_date else None

        set_field("title", getattr(details, "title", None) or movie.title)
        set_field("original_title", getattr(details, "original_title", None) or "")
        set_field("description", getattr(details, "overview", None) or "")
        set_field("release_date", release_date)
        if release_year:
            set_field("year", release_year)

        runtime = cls._safe_int(getattr(details, "runtime", None))
        set_field("duration", runtime if runtime and runtime > 0 else None)

        set_field("poster", getattr(details, "poster_path", None))
        set_field("is_ongoing", False)
        set_field("year_end", None)
        set_field("seasons_count", None)
        set_field("episodes_count", None)

        budget = cls._normalize_money(getattr(details, "budget", None))
        revenue = cls._normalize_money(getattr(details, "revenue", None))
        set_field("budget", budget)
        set_field("box_office", revenue)

    @classmethod
    def _apply_tv_payload(cls, movie: Movie, details, set_field):
        first_air_date = getattr(details, "first_air_date", None)
        first_air_year = getattr(first_air_date, "year", None) if first_air_date else None
        last_air_date = getattr(details, "last_air_date", None)
        last_air_year = getattr(last_air_date, "year", None) if last_air_date else None

        set_field("title", getattr(details, "name", None) or movie.title)
        set_field("original_title", getattr(details, "original_name", None) or "")
        set_field("description", getattr(details, "overview", None) or "")
        set_field("release_date", first_air_date)
        if first_air_year:
            set_field("year", first_air_year)

        runtime = cls._pick_tv_runtime(getattr(details, "episode_run_time", None))
        set_field("duration", runtime)

        set_field("poster", getattr(details, "poster_path", None))
        in_production = bool(getattr(details, "in_production", False))
        set_field("is_ongoing", in_production)
        set_field("year_end", None if in_production else last_air_year)

        set_field("seasons_count", cls._safe_int(getattr(details, "number_of_seasons", None)))
        set_field("episodes_count", cls._safe_int(getattr(details, "number_of_episodes", None)))

        # Для ТВ чистим movie-only поля.
        set_field("budget", None)
        set_field("box_office", None)

        if movie.movie_type == Movie.MovieType.MOVIE:
            set_field("movie_type", Movie.MovieType.SERIES)

    @classmethod
    def _sync_genres(cls, movie: Movie, tmdb_genres) -> bool:
        if tmdb_genres is None:
            return False

        genre_ids_before = set(movie.genres.values_list("id", flat=True))
        genre_objects: list[Genre] = []
        for tmdb_genre in tmdb_genres:
            name = (getattr(tmdb_genre, "name", None) or "").strip()
            if not name:
                continue
            genre, _ = Genre.objects.get_or_create(name=name)
            genre_objects.append(genre)

        movie.genres.set(genre_objects)
        genre_ids_after = set(movie.genres.values_list("id", flat=True))
        return genre_ids_before != genre_ids_after

    @classmethod
    def _sync_countries(cls, movie: Movie, countries, origin_countries) -> bool:
        source_items = list(countries or [])
        if not source_items:
            source_items = list(origin_countries or [])

        if source_items is None:
            return False

        country_ids_before = set(movie.countries.values_list("id", flat=True))
        country_objects: list[CoreCountry] = []
        for item in source_items:
            country = cls._get_or_create_core_country(item)
            if country:
                country_objects.append(country)

        movie.countries.set(country_objects)
        country_ids_after = set(movie.countries.values_list("id", flat=True))
        return country_ids_before != country_ids_after

    @classmethod
    def _get_or_create_core_country(cls, item) -> CoreCountry | None:
        code = (getattr(item, "iso_3166_1", None) or "").strip().upper()
        name = (getattr(item, "name", None) or "").strip()

        if code:
            by_code = CoreCountry.objects.filter(code=code).first()
            if by_code:
                return by_code

        if name:
            by_name = CoreCountry.objects.filter(name=name).first()
            if by_name:
                if code and not by_name.code:
                    if not CoreCountry.objects.filter(code=code).exclude(pk=by_name.pk).exists():
                        by_name.code = code
                        by_name.save(update_fields=["code"])
                return by_name

        if not code and not name:
            return None

        resolved_name = name or code
        resolved_code = code or cls._build_country_code(resolved_name)
        if CoreCountry.objects.filter(code=resolved_code).exists():
            # fallback, чтобы не нарушить unique code
            return CoreCountry.objects.filter(code=resolved_code).first()
        return CoreCountry.objects.create(name=resolved_name, code=resolved_code)

    @staticmethod
    def _build_country_code(name: str) -> str:
        letters = [ch for ch in name.upper() if "A" <= ch <= "Z"]
        if len(letters) >= 2:
            return f"{letters[0]}{letters[1]}"
        if len(letters) == 1:
            return f"{letters[0]}X"
        return "XX"

    @classmethod
    def _map_tmdb_status(cls, media_type: MediaType, tmdb_status: str | None) -> str | None:
        if not tmdb_status:
            return None
        normalized = tmdb_status.strip().lower()

        if media_type == "movie":
            return {
                "released": Movie.Status.RELEASED,
                "post production": Movie.Status.POST_PRODUCTION,
                "in production": Movie.Status.PRODUCTION,
                "planned": Movie.Status.ANNOUNCED,
                "rumored": Movie.Status.ANNOUNCED,
                "canceled": Movie.Status.CANCELLED,
            }.get(normalized)

        return {
            "ended": Movie.Status.COMPLETED,
            "returning series": Movie.Status.RELEASED,
            "in production": Movie.Status.PRODUCTION,
            "planned": Movie.Status.ANNOUNCED,
            "pilot": Movie.Status.ANNOUNCED,
            "canceled": Movie.Status.CANCELLED,
            "cancelled": Movie.Status.CANCELLED,
            "on hiatus": Movie.Status.HIATUS,
        }.get(normalized)

    @staticmethod
    def _pick_tv_runtime(values) -> int | None:
        if not values:
            return None
        for value in values:
            runtime = TMDBMovieSyncService._safe_int(value)
            if runtime and runtime > 0:
                return runtime
        return None

    @staticmethod
    def _extract_youtube_trailer_url(videos) -> str | None:
        if not videos:
            return None

        preferred = None
        fallback = None
        for video in videos:
            site = (getattr(video, "site", None) or "").lower()
            key = (getattr(video, "key", None) or "").strip()
            video_type = (getattr(video, "type", None) or "").lower()
            official = bool(getattr(video, "official", False))
            if site != "youtube" or not key:
                continue
            url = f"https://www.youtube.com/watch?v={key}"
            if video_type == "trailer" and official:
                preferred = url
                break
            if video_type == "trailer" and fallback is None:
                fallback = url
            if fallback is None:
                fallback = url
        return preferred or fallback

    @staticmethod
    def _safe_int(value) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_money(value) -> Decimal | None:
        if value is None:
            return None
        try:
            amount = Decimal(str(value))
        except Exception:
            return None

        if amount <= 0:
            return None

        # Поле max_digits=12, decimal_places=2 -> максимум 9_999_999_999.99
        max_supported = Decimal("9999999999.99")
        if amount > max_supported:
            return None
        return amount.quantize(Decimal("0.01"))
