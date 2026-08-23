from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import logging
from typing import Literal

from django.db import transaction
from django.utils import timezone
from rapidfuzz import fuzz, process

from core.models import Country as CoreCountry
from moviefilter.services.favorite_actor_matcher import (
    DEFAULT_SCORE_CUTOFF,
    normalize_actor_name,
)
from tmdb_adapter.client_singleton import get_tmdb_client
from vault.models import Genre, Movie, MoviePerson, Episode, Person, Season, UserMovie, UserSeason
from vault.services.tmdb_movie_matching_service import (
    TMDBCandidate,
    TMDBMovieMatchingService,
)
from vault.services.season_status_service import SeasonStatusService


SyncStatus = Literal["ok", "needs_confirmation", "needs_user_choice", "error"]
MediaType = Literal["movie", "tv"]
logger = logging.getLogger("vault.tmdb_sync")


@dataclass(slots=True, frozen=True)
class TMDBSyncResult:
    status: SyncStatus
    message: str
    updated_fields: tuple[str, ...] = field(default_factory=tuple)
    orphan_persons_deleted: int = 0
    selected_candidate: TMDBCandidate | None = None
    candidates: tuple[TMDBCandidate, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class PreviousPersonIndex:
    """Индекс персон, ранее привязанных к фильму, для матча по имени при синке."""

    exact_by_name: dict[str, Person]
    fuzzy_names: list[str]
    fuzzy_persons: list[Person]


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
        cls._log_start(movie)
        try:
            tmdb = get_tmdb_client()

            selection_reason = "manual" if selected_candidate is not None else "auto"
            candidate = selected_candidate
            if candidate is None:
                if movie.tmdb_id and movie.tmdb_media_type and not force_rematch:
                    selection_reason = "stored"
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
                    cls._log_match_found(match_result)
                    if match_result.status in {"needs_confirmation", "needs_user_choice"}:
                        cls._log_done(match_result.status, match_result.message)
                        return TMDBSyncResult(
                            status=match_result.status,
                            message=match_result.message,
                            candidates=match_result.candidates,
                        )
                    if match_result.status == "not_found" or match_result.selected_candidate is None:
                        msg = match_result.message or "Не удалось подобрать TMDB фильм"
                        cls._log_done("error", msg)
                        return TMDBSyncResult(
                            status="error",
                            message=msg,
                        )
                    selection_reason = "auto"
                    candidate = match_result.selected_candidate
            else:
                cls._log_match_found(None)

            cls._log_match_selected(candidate, selection_reason)
            details, media_type = cls._load_details(tmdb, candidate)
            if details is None or media_type is None:
                msg = "Не удалось загрузить детали фильма из TMDB"
                cls._log_done("error", msg)
                return TMDBSyncResult(
                    status="error",
                    message=msg,
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
            if cls._sync_movie_persons(movie=movie, details=details, tmdb=tmdb):
                relations_updated.append("movie_persons")
            if media_type == "tv":
                season_updates = cls._sync_seasons_and_episodes(movie, details, tmdb)
                if season_updates:
                    relations_updated.append("seasons")
                    relations_updated.append("episodes")
                cls._sync_season_user_statuses(movie)
            orphan_deleted_count = cls._cleanup_orphan_persons()
            if orphan_deleted_count:
                relations_updated.append("orphan_person_cleanup")

            all_updates = tuple(updated_fields + relations_updated)
            cast_count = len(list(getattr(details, "cast", None) or []))
            crew_count = len(list(getattr(details, "crew", None) or []))
            cls._log_sync_apply(all_updates, cast_count, crew_count)
            cls._log_orphan_cleanup(orphan_deleted_count)
            cls._log_done("ok", "sync completed")

            return TMDBSyncResult(
                status="ok",
                message="Данные фильма обновлены из TMDB",
                updated_fields=all_updates,
                orphan_persons_deleted=orphan_deleted_count,
                selected_candidate=candidate,
            )
        except Exception as exc:
            cls._log_done("error", f"exception: {cls._log_text(str(exc), 180)}")
            raise

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
        set_field("backdrop_path", getattr(details, "backdrop_path", None))
        set_field("is_ongoing", False)
        set_field("year_end", None)
        set_field("seasons_count", None)
        set_field("episodes_count", None)

        budget = cls._normalize_money(getattr(details, "budget", None))
        revenue = cls._normalize_money(getattr(details, "revenue", None))
        set_field("budget", budget)
        set_field("box_office", revenue)

        # Внешние ID и официальный сайт
        set_field("imdb_id", cls._clean_text(getattr(details, "imdb_id", None), 15, "") or None)
        homepage = getattr(details, "homepage", None) or None
        if not homepage and movie.tmdb_id:
            homepage = cls._fetch_homepage_fallback(movie.tmdb_id)
        set_field("homepage", homepage)
        set_field("tvdb_id", None)

        # Рейтинги TMDB
        set_field("tmdb_vote_average", cls._normalize_vote_average(getattr(details, "vote_average", None)))
        set_field("tmdb_vote_count", cls._safe_int(getattr(details, "vote_count", None)))

        # Язык TMDB
        lang_code = cls._extract_language_code(getattr(details, "original_language", None))
        set_field("tmdb_original_language", cls._clean_text(lang_code, 10, "") or None)

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
        set_field("backdrop_path", getattr(details, "backdrop_path", None))
        in_production = bool(getattr(details, "in_production", False))
        set_field("is_ongoing", in_production)
        set_field("year_end", None if in_production else last_air_year)

        set_field("seasons_count", cls._safe_int(getattr(details, "number_of_seasons", None)))
        set_field("episodes_count", cls._safe_int(getattr(details, "number_of_episodes", None)))

        # Для ТВ чистим movie-only поля.
        set_field("budget", None)
        set_field("box_office", None)

        # Внешние ID и официальный сайт
        set_field("imdb_id", cls._clean_text(getattr(details, "imdb_id", None), 15, "") or None)
        homepage = getattr(details, "homepage", None) or None
        if not homepage and movie.tmdb_id:
            homepage = cls._fetch_homepage_fallback(movie.tmdb_id)
        set_field("homepage", homepage)
        set_field("tvdb_id", cls._safe_int(getattr(details, "tvdb_id", None)))

        # Рейтинги TMDB
        set_field("tmdb_vote_average", cls._normalize_vote_average(getattr(details, "vote_average", None)))
        set_field("tmdb_vote_count", cls._safe_int(getattr(details, "vote_count", None)))

        # Язык TMDB
        lang_code = cls._extract_language_code(getattr(details, "original_language", None))
        set_field("tmdb_original_language", cls._clean_text(lang_code, 10, "") or None)

        tmdb_type = (getattr(details, "type", None) or "").strip().lower()
        target_type = (
            Movie.MovieType.MINISERIES if tmdb_type == "miniseries" else Movie.MovieType.SERIES
        )
        if movie.movie_type in (Movie.MovieType.MOVIE, Movie.MovieType.SERIES) and movie.movie_type != target_type:
            set_field("movie_type", target_type)

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
    def _sync_movie_persons(cls, movie: Movie, details, tmdb) -> bool:
        cast_items = list(getattr(details, "cast", None) or [])
        crew_items = list(getattr(details, "crew", None) or [])

        # Для сериалов главная фигура за проектом — создатель (created_by) из TMDB.
        # Режиссёров эпизодов (aggregate_credits) для сериала не берём: они не релевантны
        # сериалу как целому, в обычных credits на уровне сериала их и так нет.
        is_tv = movie.tmdb_media_type == "tv" or movie.movie_type in (
            Movie.MovieType.SERIES,
            Movie.MovieType.MINISERIES,
        )
        director_items = list(getattr(details, "created_by", None) or []) if is_tv else []

        before_keys = set(
            movie.movie_persons.values_list("person_id", "role", "character_name")
        )

        previous_persons = list(
            Person.objects.filter(person_movies__movie=movie).distinct()
        )
        previous_index = cls._build_previous_person_index(previous_persons)

        movie.movie_persons.all().delete()

        unknown_country = cls._get_unknown_country()
        person_cache: dict[int, Person] = {}
        person_details_cache: dict[int, object | None] = {}
        seen_relations: set[tuple[int, str, str]] = set()

        for credit in cast_items:
            person = cls._upsert_person_from_credit(
                tmdb=tmdb,
                credit=credit,
                unknown_country=unknown_country,
                person_cache=person_cache,
                person_details_cache=person_details_cache,
                previous_index=previous_index,
            )
            if not person:
                continue

            character_name = cls._clean_text(getattr(credit, "character", None), 255, "")
            relation_key = (person.id, "actor", character_name)
            if relation_key in seen_relations:
                continue

            seen_relations.add(relation_key)
            order = cls._safe_int(getattr(credit, "order", None)) or 0
            MoviePerson.objects.create(
                movie=movie,
                person=person,
                role="actor",
                character_name=character_name,
                order=order,
            )

        for credit in director_items:
            person = cls._upsert_person_from_credit(
                tmdb=tmdb,
                credit=credit,
                unknown_country=unknown_country,
                person_cache=person_cache,
                person_details_cache=person_details_cache,
                previous_index=previous_index,
            )
            if not person:
                continue

            relation_key = (person.id, "director", "")
            if relation_key in seen_relations:
                continue

            seen_relations.add(relation_key)
            order = cls._safe_int(getattr(credit, "order", None)) or 0
            MoviePerson.objects.create(
                movie=movie,
                person=person,
                role="director",
                character_name="",
                order=order,
            )

        for credit in crew_items:
            role = cls._map_crew_role(getattr(credit, "job", None))
            if not role:
                continue

            person = cls._upsert_person_from_credit(
                tmdb=tmdb,
                credit=credit,
                unknown_country=unknown_country,
                person_cache=person_cache,
                person_details_cache=person_details_cache,
                previous_index=previous_index,
            )
            if not person:
                continue

            relation_key = (person.id, role, "")
            if relation_key in seen_relations:
                continue

            seen_relations.add(relation_key)
            order = cls._safe_int(getattr(credit, "order", None)) or 0
            MoviePerson.objects.create(
                movie=movie,
                person=person,
                role=role,
                character_name="",
                order=order,
            )

        after_keys = set(
            movie.movie_persons.values_list("person_id", "role", "character_name")
        )
        return before_keys != after_keys

    @classmethod
    def _build_previous_person_index(
        cls, previous_persons: list[Person]
    ) -> PreviousPersonIndex | None:
        """
        Строит индекс персон, ранее привязанных к фильму, для матча по имени.

        Используется как fallback, когда TMDB-персона не нашлась по tmdb_id/imdb_id
        (например, персона была создана из CSV-импорта с синтетическими ID).
        Переиспользование той же персоны сохраняет пользовательские данные
        (FavoritePerson, заметки и т.д.).
        """
        exact_by_name: dict[str, Person] = {}
        fuzzy_names: list[str] = []
        fuzzy_persons: list[Person] = []
        for person in previous_persons:
            for raw in (person.name, person.original_name):
                clean = normalize_actor_name(raw)
                if not clean or clean in exact_by_name:
                    continue
                exact_by_name[clean] = person
                fuzzy_names.append(clean)
                fuzzy_persons.append(person)
        if not fuzzy_names:
            return None
        return PreviousPersonIndex(
            exact_by_name=exact_by_name,
            fuzzy_names=fuzzy_names,
            fuzzy_persons=fuzzy_persons,
        )

    @classmethod
    def _match_person_by_name(
        cls,
        candidate_names: tuple[str, ...],
        index: PreviousPersonIndex,
    ) -> Person | None:
        """Матч TMDB-персоны по имени среди персон, ранее привязанных к фильму."""
        for candidate in candidate_names:
            clean = normalize_actor_name(candidate)
            if not clean:
                continue
            person = index.exact_by_name.get(clean)
            if person is not None:
                return person

        for candidate in candidate_names:
            clean = normalize_actor_name(candidate)
            if not clean:
                continue
            match = process.extractOne(
                clean,
                index.fuzzy_names,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=DEFAULT_SCORE_CUTOFF,
            )
            if match is not None:
                return index.fuzzy_persons[match[2]]
        return None

    @classmethod
    def _cleanup_orphan_persons(cls) -> int:
        """
        Удаляет персон без связей в MoviePerson.
        Персоны из FavoritePerson защищены от удаления.
        """
        orphan_qs = Person.objects.filter(
            person_movies__isnull=True,
            favorited_by__isnull=True,
        ).distinct()
        count = orphan_qs.count()
        if count:
            orphan_qs.delete()
        return count

    # ------------------------------------ #
    #            DOMAIN LAYER              #
    # ------------------------------------ #

    @classmethod
    def _sync_seasons_and_episodes(cls, movie: Movie, details, tmdb) -> bool:
        """
        Синхронизирует сезоны и эпизоды для сериала из TMDB.
        Обновляет существующие Season/Episode и создает новые.
        Возвращает True, если были изменения.
        """
        tmdb_id = cls._safe_int(getattr(details, "id", None) or movie.tmdb_id)
        if not tmdb_id:
            return False

        tmdb_seasons = getattr(details, "seasons", None)
        if not tmdb_seasons:
            return False

        changed = False

        for tmdb_season in tmdb_seasons:
            season_number = cls._safe_int(getattr(tmdb_season, "season_number", None))
            if season_number is None:
                continue

            season, created = Season.objects.get_or_create(
                movie=movie,
                season_number=season_number,
                defaults={
                    "title": cls._clean_text(getattr(tmdb_season, "name", None), 255, ""),
                    "description": (getattr(tmdb_season, "overview", None) or "").strip(),
                    "release_date": getattr(tmdb_season, "air_date", None),
                    "poster": getattr(tmdb_season, "poster_path", None),
                    "source": Movie.Source.TMDB,
                },
            )

            if not created:
                updated = False
                new_title = cls._clean_text(getattr(tmdb_season, "name", None), 255, "")
                new_desc = (getattr(tmdb_season, "overview", None) or "").strip()
                new_poster = getattr(tmdb_season, "poster_path", None)
                new_release = getattr(tmdb_season, "air_date", None)

                if season.title != new_title:
                    season.title = new_title
                    updated = True
                if season.description != new_desc:
                    season.description = new_desc
                    updated = True
                if season.poster != new_poster:
                    season.poster = new_poster
                    updated = True
                if season.release_date != new_release:
                    season.release_date = new_release
                    updated = True
                if updated:
                    season.save(update_fields=["title", "description", "poster", "release_date"])
                    changed = True

            # Load episode details
            try:
                season_details = tmdb.tv_season(tmdb_id, season_number)
            except Exception:
                season_details = None

            tmdb_episodes = getattr(season_details, "episodes", None)
            if tmdb_episodes:
                changed = cls._sync_episodes(season, tmdb_episodes) or changed

        # Remove seasons that no longer exist in TMDB
        tmdb_season_numbers = {
            cls._safe_int(getattr(s, "season_number", None))
            for s in tmdb_seasons
            if cls._safe_int(getattr(s, "season_number", None)) is not None
        }
        orphaned_seasons = movie.seasons.exclude(season_number__in=tmdb_season_numbers)
        if orphaned_seasons.exists():
            orphaned_seasons.delete()
            changed = True

        return changed

    @classmethod
    def _sync_episodes(cls, season: Season, tmdb_episodes) -> bool:
        """Синхронизирует эпизоды сезона из TMDB."""
        if not tmdb_episodes:
            return False

        tmdb_episode_map = {}
        for tmdb_ep in tmdb_episodes:
            ep_num = cls._safe_int(getattr(tmdb_ep, "episode_number", None))
            if ep_num is not None:
                tmdb_episode_map[ep_num] = tmdb_ep

        changed = False

        # Create or update episodes
        for ep_num, tmdb_ep in tmdb_episode_map.items():
            episode, created = Episode.objects.get_or_create(
                season=season,
                episode_number=ep_num,
                defaults={
                    "title": cls._clean_text(getattr(tmdb_ep, "name", None), 255, ""),
                    "description": (getattr(tmdb_ep, "overview", None) or "").strip(),
                    "duration": cls._safe_int(getattr(tmdb_ep, "runtime", None)),
                    "release_date": getattr(tmdb_ep, "air_date", None),
                },
            )

            if not created:
                updated = False
                new_title = cls._clean_text(getattr(tmdb_ep, "name", None), 255, "")
                new_desc = (getattr(tmdb_ep, "overview", None) or "").strip()
                new_duration = cls._safe_int(getattr(tmdb_ep, "runtime", None))
                new_release = getattr(tmdb_ep, "air_date", None)

                if episode.title != new_title:
                    episode.title = new_title
                    updated = True
                if episode.description != new_desc:
                    episode.description = new_desc
                    updated = True
                if episode.duration != new_duration:
                    episode.duration = new_duration
                    updated = True
                if episode.release_date != new_release:
                    episode.release_date = new_release
                    updated = True
                if updated:
                    episode.save(update_fields=["title", "description", "duration", "release_date"])
                    changed = True

        # Remove episodes that no longer exist in TMDB
        existing_numbers = set(
            Episode.objects.filter(season=season).values_list("episode_number", flat=True)
        )
        tmdb_numbers = set(tmdb_episode_map.keys())
        orphaned_numbers = existing_numbers - tmdb_numbers
        if orphaned_numbers:
            Episode.objects.filter(season=season, episode_number__in=orphaned_numbers).delete()
            changed = True

        return changed

    @classmethod
    def _sync_season_user_statuses(cls, movie: Movie) -> None:
        """
        Синхронизирует статусы сезонов на основе статуса сериала у каждого пользователя.
        Если сериал просмотрен — все сезоны отмечаются как просмотренные.
        Если сериал в планах — сезоны в планы.
        Если сериал пропущен — сезоны пропущены.
        """
        if movie.movie_type not in (Movie.MovieType.SERIES, Movie.MovieType.MINISERIES):
            return

        for user_movie in movie.user_movies.exclude(watch_status=None):
            watch_status_key = (
                "watched" if user_movie.watch_status == UserMovie.WatchStatus.WATCHED
                else "skip" if user_movie.watch_status == UserMovie.WatchStatus.SKIP
                else "plan" if user_movie.watch_status == UserMovie.WatchStatus.PLAN
                else None
            )
            if watch_status_key is None:
                continue
            SeasonStatusService.sync_statuses_from_user_movie(
                user=user_movie.user,
                movie=movie,
                watch_status_key=watch_status_key,
            )

    @classmethod
    def _upsert_person_from_credit(
        cls,
        tmdb,
        credit,
        unknown_country: CoreCountry,
        person_cache: dict[int, Person],
        person_details_cache: dict[int, object | None],
        previous_index: PreviousPersonIndex | None = None,
    ) -> Person | None:
        person_id = cls._safe_int(getattr(credit, "person_id", None))
        if not person_id:
            return None

        if person_id in person_cache:
            return person_cache[person_id]

        details = cls._load_person_details(tmdb, person_id, person_details_cache)
        tmdb_id = cls._normalize_tmdb_person_id(person_id)
        if not tmdb_id:
            return None

        imdb_id = cls._normalize_imdb_id(getattr(details, "imdb_id", None))
        if not imdb_id:
            imdb_id = cls._fallback_imdb_id(tmdb_id)

        person = Person.objects.filter(tmdb_id=tmdb_id).first()
        if person is None:
            person = Person.objects.filter(imdb_id=imdb_id).first()

        name = cls._clean_text(
            cls._first_non_empty(getattr(details, "name", None), getattr(credit, "name", None)),
            100,
            "Unknown",
        )
        original_name = cls._clean_text(
            cls._first_non_empty(getattr(credit, "original_name", None), getattr(details, "name", None), name),
            100,
            name,
        )

        if person is None and previous_index is not None:
            person = cls._match_person_by_name(
                candidate_names=(
                    name,
                    original_name,
                    cls._clean_text(getattr(credit, "name", None), 100, ""),
                    cls._clean_text(getattr(credit, "original_name", None), 100, ""),
                    cls._clean_text(getattr(details, "name", None), 100, ""),
                ),
                index=previous_index,
            )

        photo = cls._first_non_empty(getattr(details, "profile_path", None), getattr(credit, "profile_path", None))
        gender = cls._map_person_gender(
            cls._safe_int(cls._first_non_empty(getattr(details, "gender", None), getattr(credit, "gender", None)))
        )
        birth_date = getattr(details, "birthday", None)
        death_date = getattr(details, "deathday", None)
        biography = getattr(details, "biography", None) if details is not None else None

        if person is None:
            imdb_id = cls._ensure_unique_imdb_id(imdb_id)
            person = Person.objects.create(
                tmdb_id=tmdb_id,
                imdb_id=imdb_id,
                name=name,
                original_name=original_name,
                birth_date=birth_date,
                death_date=death_date,
                gender=gender,
                photo=photo,
                biography=biography or "",
                country=unknown_country,
            )
            person_cache[person_id] = person
            return person

        update_fields: list[str] = []
        if person.tmdb_id != tmdb_id:
            if not Person.objects.filter(tmdb_id=tmdb_id).exclude(pk=person.pk).exists():
                person.tmdb_id = tmdb_id
                update_fields.append("tmdb_id")

        if person.imdb_id != imdb_id:
            if not Person.objects.filter(imdb_id=imdb_id).exclude(pk=person.pk).exists():
                person.imdb_id = imdb_id
                update_fields.append("imdb_id")

        if person.name != name:
            person.name = name
            update_fields.append("name")

        if person.original_name != original_name:
            person.original_name = original_name
            update_fields.append("original_name")

        if person.birth_date != birth_date:
            person.birth_date = birth_date
            update_fields.append("birth_date")

        if person.death_date != death_date:
            person.death_date = death_date
            update_fields.append("death_date")

        if person.gender != gender:
            person.gender = gender
            update_fields.append("gender")

        if person.photo != photo:
            person.photo = photo
            update_fields.append("photo")

        if biography is not None and person.biography != biography:
            person.biography = biography
            update_fields.append("biography")

        if not person.country_id:
            person.country = unknown_country
            update_fields.append("country")

        if update_fields:
            person.save(update_fields=update_fields)

        person_cache[person_id] = person
        return person

    @classmethod
    def _load_person_details(cls, tmdb, person_id: int, cache: dict[int, object | None]):
        if person_id in cache:
            return cache[person_id]

        try:
            details = tmdb.person(person_id)
        except Exception:
            details = None

        cache[person_id] = details
        return details

    @classmethod
    def _map_crew_role(cls, job: str | None) -> str | None:
        normalized = (job or "").strip().lower()
        if not normalized:
            return None

        if normalized == "director":
            return "director"
        if normalized in {"producer", "executive producer"}:
            return "producer"
        if normalized in {"writer", "screenplay", "story"}:
            return "writer"
        if normalized == "original music composer":
            return "composer"
        if normalized == "director of photography":
            return "operator"
        if normalized == "editor":
            return "editor"
        return None

    @classmethod
    def _normalize_tmdb_person_id(cls, person_id: int | str | None) -> str | None:
        value = cls._safe_int(person_id)
        if not value:
            return None

        text = str(value)
        if len(text) <= 10:
            return text

        # Ограничение модели Person.tmdb_id(max_length=10).
        encoded = cls._to_base36(value)
        return cls._clean_text(f"t{encoded}", 10, "")

    @classmethod
    def _normalize_imdb_id(cls, imdb_id: str | None) -> str | None:
        value = (imdb_id or "").strip()
        if not value:
            return None
        return cls._clean_text(value, 10, "")

    @classmethod
    def _fallback_imdb_id(cls, tmdb_id: str) -> str:
        numeric = cls._safe_int(tmdb_id)
        if numeric is None:
            base = cls._clean_text(tmdb_id, 8, "00000000")
            return f"tm{base}"[:10]
        return f"tm{cls._to_base36(numeric)}"[:10]

    @classmethod
    def _ensure_unique_imdb_id(cls, imdb_id: str) -> str:
        if not Person.objects.filter(imdb_id=imdb_id).exists():
            return imdb_id

        prefix = imdb_id[:8]
        for idx in range(1, 100):
            candidate = f"{prefix}{idx:02d}"[:10]
            if not Person.objects.filter(imdb_id=candidate).exists():
                return candidate
        return imdb_id

    @classmethod
    def _get_unknown_country(cls) -> CoreCountry:
        by_name = CoreCountry.objects.filter(name="Unknown").first()
        if by_name:
            return by_name

        by_code = CoreCountry.objects.filter(code="XX").first()
        if by_code:
            return by_code

        return CoreCountry.objects.create(name="Unknown", code="XX")

    @staticmethod
    def _map_person_gender(gender: int | None) -> str:
        if gender == 2:
            return "M"
        if gender == 1:
            return "F"
        return ""

    @staticmethod
    def _clean_text(value, max_len: int, default: str = "") -> str:
        text = (value or "").strip()
        if not text:
            return default
        return text[:max_len]

    @staticmethod
    def _first_non_empty(*values):
        for value in values:
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _to_base36(value: int) -> str:
        alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
        if value == 0:
            return "0"
        digits: list[str] = []
        number = value
        while number:
            number, rem = divmod(number, 36)
            digits.append(alphabet[rem])
        return "".join(reversed(digits))

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

    @staticmethod
    def _normalize_vote_average(value) -> Decimal | None:
        if value is None:
            return None
        try:
            amount = Decimal(str(value))
        except Exception:
            return None

        if amount < 0:
            return None

        # Поле max_digits=3, decimal_places=1 -> максимум 99.9
        if amount > Decimal("99.9"):
            return None
        return amount.quantize(Decimal("0.1"))

    @staticmethod
    def _fetch_homepage_fallback(tmdb_id: int) -> str | None:
        """TMDB возвращает пустой homepage при ненулевых языках (en-US — исключение).

        Делает один лайтвейт-запрос с ``language=en-US`` только для этого поля.
        """
        try:
            from moviefilter.models import UserPreferences
            import requests as _req

            api_key = UserPreferences.get().tmdb_api_key
            if not api_key:
                return None
            resp = _req.get(
                f"https://api.themoviedb.org/3/movie/{tmdb_id}",
                params={"api_key": api_key, "language": "en-US"},
                headers={"accept": "application/json"},
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            return resp.json().get("homepage") or None
        except Exception:
            logger.debug("homepage fallback failed for tmdb_id=%s", tmdb_id, exc_info=True)
            return None

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

    @classmethod
    def _log_start(cls, movie: Movie) -> None:
        cls._emit_log(
            f'SYNC_START | movie_id={movie.id} | title="{cls._log_text(movie.title, 90)}" '
            f'| orig="{cls._log_text(movie.original_title, 90)}" | year={movie.year or ""}'
        )

    @classmethod
    def _log_match_found(cls, match_result) -> None:
        if match_result is None:
            cls._emit_log("MATCH_FOUND | candidates=- | top=[]")
            return
        candidates = match_result.candidates or ()
        top = ",".join([f"{c.tmdb_id}:{c.score}" for c in candidates[:5]])
        cls._emit_log(f"MATCH_FOUND | candidates={len(candidates)} | top=[{top}]")

    @classmethod
    def _log_match_selected(cls, candidate: TMDBCandidate, reason: str) -> None:
        cls._emit_log(
            f"MATCH_SELECTED | tmdb_id={candidate.tmdb_id} | media={candidate.media_type} | reason={reason}"
        )

    @classmethod
    def _log_sync_apply(cls, updated_fields: tuple[str, ...], cast_count: int, crew_count: int) -> None:
        updated_text = ",".join(updated_fields) if updated_fields else "-"
        cls._emit_log(
            f"SYNC_APPLY | updated={updated_text} | cast={cast_count} | crew={crew_count}"
        )

    @classmethod
    def _log_orphan_cleanup(cls, deleted_count: int) -> None:
        cls._emit_log(f"ORPHAN_CLEANUP | deleted={deleted_count}")

    @classmethod
    def _log_done(cls, status: str, msg: str) -> None:
        cls._emit_log(f'SYNC_DONE | status={status} | msg="{cls._log_text(msg, 220)}"')

    @classmethod
    def _emit_log(cls, line: str) -> None:
        logger.info(line)
        print(line, flush=True)

    @staticmethod
    def _log_text(value, limit: int = 120) -> str:
        text = str(value or "").replace("\n", " ").replace("\r", " ").replace('"', "'").strip()
        if len(text) > limit:
            return text[: limit - 1] + "…"
        return text
