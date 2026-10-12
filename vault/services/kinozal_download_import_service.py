from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

from django.db import transaction

from moviefilter.models import MovieRSS
from vault.models import Movie, VaultConnectionEvent
from vault.services.movie_status_service import MovieStatusService
from vault.services.tmdb_movie_import_service import TMDBMovieImportService
from vault.services.tmdb_movie_matching_service import TMDBMovieMatchingService, TMDBMatchingResult
from vault.services.tmdb_movie_sync_service import TMDBMovieSyncService
from vault.constants import WONT_WATCH_LABEL


ImportStatus = Literal["created", "reused", "not_found", "ambiguous", "error"]
QueueStatus = Literal["queued", "error"]


@dataclass(slots=True, frozen=True)
class KinozalDownloadImportResult:
    operation_id: UUID
    status: ImportStatus
    message: str
    movie: Movie | None = None


@dataclass(slots=True, frozen=True)
class KinozalDownloadEnqueueResult:
    operation_id: UUID
    status: QueueStatus
    message: str


class KinozalDownloadImportService:
    # ------------------------------------ #
    #          APPLICATION LAYER           #
    # ------------------------------------ #

    @classmethod
    def enqueue_successful_download(
        cls,
        *,
        movie_rss_id: int,
        torrent_id: int,
        user,
        saved_to: str,
    ) -> KinozalDownloadEnqueueResult:
        operation_id = uuid4()
        movie_rss = MovieRSS.objects.filter(pk=movie_rss_id).first()
        if movie_rss is None:
            cls._log(
                operation_id=operation_id,
                level=VaultConnectionEvent.Level.ERROR,
                event_type="rss_movie_missing",
                message=f"MovieRSS #{movie_rss_id} не найден",
                torrent_id=torrent_id,
                user=user,
            )
            return KinozalDownloadEnqueueResult(
                operation_id=operation_id,
                status="error",
                message="MovieRSS не найден",
            )

        cls._log(
            operation_id=operation_id,
            level=VaultConnectionEvent.Level.INFO,
            event_type="download_saved",
            message=f"Torrent сохранен: {saved_to}",
            movie_rss=movie_rss,
            torrent_id=torrent_id,
            user=user,
            payload={"saved_to": saved_to},
        )
        try:
            from vault.tasks import process_kinozal_download_import

            process_kinozal_download_import(
                str(operation_id),
                movie_rss_id,
                torrent_id,
                user.id if getattr(user, "is_authenticated", False) else None,
                saved_to,
            )
        except Exception as exc:
            cls._log(
                operation_id=operation_id,
                level=VaultConnectionEvent.Level.ERROR,
                event_type="import_queue_failed",
                message=f"Не удалось поставить импорт в очередь: {exc}",
                movie_rss=movie_rss,
                torrent_id=torrent_id,
                user=user,
                payload={"error_type": type(exc).__name__},
            )
            return KinozalDownloadEnqueueResult(
                operation_id=operation_id,
                status="error",
                message="Torrent сохранен, но импорт в Vault не удалось поставить в очередь",
            )

        cls._log(
            operation_id=operation_id,
            level=VaultConnectionEvent.Level.INFO,
            event_type="import_queued",
            message="Импорт в Vault поставлен в очередь",
            movie_rss=movie_rss,
            torrent_id=torrent_id,
            user=user,
            payload={"saved_to": saved_to},
        )
        return KinozalDownloadEnqueueResult(
            operation_id=operation_id,
            status="queued",
            message="Torrent сохранен. Импорт в Vault поставлен в очередь",
        )

    @classmethod
    @transaction.atomic
    def handle_successful_download(
        cls,
        *,
        movie_rss_id: int,
        torrent_id: int,
        user,
        saved_to: str,
        operation_id: UUID | None = None,
        log_download_saved: bool = True,
    ) -> KinozalDownloadImportResult:
        operation_id = operation_id or uuid4()
        movie_rss = MovieRSS.objects.filter(pk=movie_rss_id).first()
        if movie_rss is None:
            cls._log(
                operation_id=operation_id,
                level=VaultConnectionEvent.Level.ERROR,
                event_type="rss_movie_missing",
                message=f"MovieRSS #{movie_rss_id} не найден",
                torrent_id=torrent_id,
                user=user,
            )
            return KinozalDownloadImportResult(
                operation_id=operation_id,
                status="error",
                message="MovieRSS не найден",
            )

        if log_download_saved:
            cls._log(
                operation_id=operation_id,
                level=VaultConnectionEvent.Level.INFO,
                event_type="download_saved",
                message=f"Torrent сохранен: {saved_to}",
                movie_rss=movie_rss,
                torrent_id=torrent_id,
                user=user,
                payload={"saved_to": saved_to},
            )
        else:
            cls._log(
                operation_id=operation_id,
                level=VaultConnectionEvent.Level.INFO,
                event_type="background_import_started",
                message="Фоновый импорт в Vault запущен",
                movie_rss=movie_rss,
                torrent_id=torrent_id,
                user=user,
                payload={"saved_to": saved_to},
            )

        movie = cls._find_existing_movie(movie_rss, operation_id=operation_id, torrent_id=torrent_id, user=user)
        candidate = None
        if movie is None or not movie.tmdb_id:
            match_result = cls._resolve_tmdb_match(movie_rss, operation_id=operation_id, torrent_id=torrent_id, user=user)
            if match_result is not None and match_result.selected_candidate is not None:
                candidate = match_result.selected_candidate
            elif movie is None:
                status = "ambiguous" if match_result and match_result.status == "needs_user_choice" else "not_found"
                message = match_result.message if match_result else "Не удалось подобрать фильм на TMDB"
                cls._log(
                    operation_id=operation_id,
                    level=VaultConnectionEvent.Level.WARNING if status == "ambiguous" else VaultConnectionEvent.Level.ERROR,
                    event_type="tmdb_resolution_stopped",
                    message=message,
                    movie_rss=movie_rss,
                    torrent_id=torrent_id,
                    user=user,
                )
                return KinozalDownloadImportResult(
                    operation_id=operation_id,
                    status=status,
                    message=message,
                )

        if movie is None and candidate is not None:
            import_result = TMDBMovieImportService.import_movie(candidate.tmdb_id, candidate.media_type)
            movie = import_result.movie
            cls._log(
                operation_id=operation_id,
                level=VaultConnectionEvent.Level.SUCCESS if import_result.status == "created" else VaultConnectionEvent.Level.INFO,
                event_type="vault_movie_imported",
                message=import_result.message,
                movie_rss=movie_rss,
                vault_movie=movie,
                torrent_id=torrent_id,
                user=user,
                tmdb_id=candidate.tmdb_id,
            )

        if movie is not None and candidate is not None and (not movie.tmdb_id or movie.tmdb_id != candidate.tmdb_id):
            sync_result = TMDBMovieSyncService.sync_movie(
                movie=movie,
                force_rematch=True,
                selected_candidate=candidate,
            )
            if sync_result.status != "ok":
                cls._log(
                    operation_id=operation_id,
                    level=VaultConnectionEvent.Level.ERROR,
                    event_type="tmdb_sync_failed",
                    message=sync_result.message,
                    movie_rss=movie_rss,
                    vault_movie=movie,
                    torrent_id=torrent_id,
                    user=user,
                    tmdb_id=candidate.tmdb_id,
                )
                return KinozalDownloadImportResult(
                    operation_id=operation_id,
                    status="error",
                    message=sync_result.message,
                    movie=movie,
                )
            movie.refresh_from_db()
            cls._log(
                operation_id=operation_id,
                level=VaultConnectionEvent.Level.SUCCESS,
                event_type="tmdb_sync_completed",
                message=sync_result.message,
                movie_rss=movie_rss,
                vault_movie=movie,
                torrent_id=torrent_id,
                user=user,
                tmdb_id=movie.tmdb_id,
                payload={"updated_fields": list(sync_result.updated_fields)},
            )

        if movie is None:
            cls._log(
                operation_id=operation_id,
                level=VaultConnectionEvent.Level.ERROR,
                event_type="vault_movie_missing",
                message="После обработки TMDB фильм в Vault не определен",
                movie_rss=movie_rss,
                torrent_id=torrent_id,
                user=user,
            )
            return KinozalDownloadImportResult(
                operation_id=operation_id,
                status="error",
                message="Не удалось определить фильм в Vault",
            )

        cls._persist_external_ids(movie, movie_rss)
        MovieStatusService.set_status(user, movie, "will_watch")
        cls._log(
            operation_id=operation_id,
            level=VaultConnectionEvent.Level.SUCCESS,
            event_type="will_watch_applied",
            message="Статус 'Буду смотреть' выставлен",
            movie_rss=movie_rss,
            vault_movie=movie,
            torrent_id=torrent_id,
            user=user,
            tmdb_id=movie.tmdb_id,
        )

        final_status: ImportStatus = "created" if candidate is not None and movie.source == Movie.Source.TMDB else "reused"
        final_message = "Фильм обработан и статус выставлен"
        cls._log(
            operation_id=operation_id,
            level=VaultConnectionEvent.Level.SUCCESS,
            event_type="operation_completed",
            message=final_message,
            movie_rss=movie_rss,
            vault_movie=movie,
            torrent_id=torrent_id,
            user=user,
            tmdb_id=movie.tmdb_id,
        )
        return KinozalDownloadImportResult(
            operation_id=operation_id,
            status=final_status,
            message=final_message,
            movie=movie,
        )

    @classmethod
    def enqueue_hide_action(
        cls,
        *,
        movie_rss_id: int,
        user,
    ) -> KinozalDownloadEnqueueResult:
        operation_id = uuid4()
        movie_rss = MovieRSS.objects.filter(pk=movie_rss_id).first()
        if movie_rss is None:
            cls._log(
                operation_id=operation_id,
                level=VaultConnectionEvent.Level.ERROR,
                event_type="rss_movie_missing",
                message=f"MovieRSS #{movie_rss_id} не найден",
                torrent_id=0,
                user=user,
            )
            return KinozalDownloadEnqueueResult(
                operation_id=operation_id,
                status="error",
                message="MovieRSS не найден",
            )

        cls._log(
            operation_id=operation_id,
            level=VaultConnectionEvent.Level.INFO,
            event_type="hide_requested",
            message=f"Hide requested for '{movie_rss.title}'",
            torrent_id=0,
            movie_rss=movie_rss,
            user=user,
        )
        try:
            from vault.tasks import process_kinozal_hide_action

            process_kinozal_hide_action(
                str(operation_id),
                movie_rss_id,
                user.id if getattr(user, "is_authenticated", False) else None,
            )
        except Exception as exc:
            cls._log(
                operation_id=operation_id,
                level=VaultConnectionEvent.Level.ERROR,
                event_type="import_queue_failed",
                message=f"Не удалось поставить hide-импорт в очередь: {exc}",
                torrent_id=0,
                movie_rss=movie_rss,
                user=user,
                payload={"error_type": type(exc).__name__},
            )
            return KinozalDownloadEnqueueResult(
                operation_id=operation_id,
                status="error",
                message="Hide запрос принят, но импорт в Vault не удалось поставить в очередь",
            )

        cls._log(
            operation_id=operation_id,
            level=VaultConnectionEvent.Level.INFO,
            event_type="import_queued",
            message="Hide-импорт в Vault поставлен в очередь",
            torrent_id=0,
            movie_rss=movie_rss,
            user=user,
        )
        return KinozalDownloadEnqueueResult(
            operation_id=operation_id,
            status="queued",
            message="Hide запрос принят. Импорт в Vault поставлен в очередь",
        )

    @classmethod
    @transaction.atomic
    def handle_hide_action(
        cls,
        *,
        movie_rss_id: int,
        user,
        operation_id: UUID | None = None,
    ) -> KinozalDownloadImportResult:
        operation_id = operation_id or uuid4()
        movie_rss = MovieRSS.objects.filter(pk=movie_rss_id).first()
        if movie_rss is None:
            cls._log(
                operation_id=operation_id,
                level=VaultConnectionEvent.Level.ERROR,
                event_type="rss_movie_missing",
                message=f"MovieRSS #{movie_rss_id} не найден",
                torrent_id=0,
                user=user,
            )
            return KinozalDownloadImportResult(
                operation_id=operation_id,
                status="error",
                message="MovieRSS не найден",
            )

        cls._log(
            operation_id=operation_id,
            level=VaultConnectionEvent.Level.INFO,
            event_type="background_import_started",
            message="Фоновый hide-импорт в Vault запущен",
            torrent_id=0,
            movie_rss=movie_rss,
            user=user,
        )

        movie = cls._find_existing_movie(movie_rss, operation_id=operation_id, torrent_id=0, user=user)
        candidate = None
        if movie is None or not movie.tmdb_id:
            match_result = cls._resolve_tmdb_match(movie_rss, operation_id=operation_id, torrent_id=0, user=user)
            if match_result is not None and match_result.selected_candidate is not None:
                candidate = match_result.selected_candidate
            elif movie is None:
                status = "ambiguous" if match_result and match_result.status == "needs_user_choice" else "not_found"
                message = match_result.message if match_result else "Не удалось подобрать фильм на TMDB"
                cls._log(
                    operation_id=operation_id,
                    level=VaultConnectionEvent.Level.WARNING if status == "ambiguous" else VaultConnectionEvent.Level.ERROR,
                    event_type="tmdb_resolution_stopped",
                    message=message,
                    torrent_id=0,
                    movie_rss=movie_rss,
                    user=user,
                )
                return KinozalDownloadImportResult(
                    operation_id=operation_id,
                    status=status,
                    message=message,
                )

        if movie is None and candidate is not None:
            import_result = TMDBMovieImportService.import_movie(candidate.tmdb_id, candidate.media_type)
            movie = import_result.movie
            cls._log(
                operation_id=operation_id,
                level=VaultConnectionEvent.Level.SUCCESS if import_result.status == "created" else VaultConnectionEvent.Level.INFO,
                event_type="vault_movie_imported",
                message=import_result.message,
                torrent_id=0,
                movie_rss=movie_rss,
                vault_movie=movie,
                user=user,
                tmdb_id=candidate.tmdb_id,
            )

        if movie is not None and candidate is not None and (not movie.tmdb_id or movie.tmdb_id != candidate.tmdb_id):
            sync_result = TMDBMovieSyncService.sync_movie(
                movie=movie,
                force_rematch=True,
                selected_candidate=candidate,
            )
            if sync_result.status != "ok":
                cls._log(
                    operation_id=operation_id,
                    level=VaultConnectionEvent.Level.ERROR,
                    event_type="tmdb_sync_failed",
                    message=sync_result.message,
                    torrent_id=0,
                    movie_rss=movie_rss,
                    vault_movie=movie,
                    user=user,
                    tmdb_id=candidate.tmdb_id,
                )
                return KinozalDownloadImportResult(
                    operation_id=operation_id,
                    status="error",
                    message=sync_result.message,
                    movie=movie,
                )
            movie.refresh_from_db()
            cls._log(
                operation_id=operation_id,
                level=VaultConnectionEvent.Level.SUCCESS,
                event_type="tmdb_sync_completed",
                message=sync_result.message,
                torrent_id=0,
                movie_rss=movie_rss,
                vault_movie=movie,
                user=user,
                tmdb_id=movie.tmdb_id,
                payload={"updated_fields": list(sync_result.updated_fields)},
            )

        if movie is None:
            cls._log(
                operation_id=operation_id,
                level=VaultConnectionEvent.Level.ERROR,
                event_type="vault_movie_missing",
                message="После обработки TMDB фильм в Vault не определен",
                torrent_id=0,
                movie_rss=movie_rss,
                user=user,
            )
            return KinozalDownloadImportResult(
                operation_id=operation_id,
                status="error",
                message="Не удалось определить фильм в Vault",
            )

        cls._persist_external_ids(movie, movie_rss)
        MovieStatusService.set_status(user, movie, "wont_watch")
        cls._log(
            operation_id=operation_id,
            level=VaultConnectionEvent.Level.SUCCESS,
            event_type="wont_watch_applied",
            message=f"Статус '{WONT_WATCH_LABEL}' выставлен",
            torrent_id=0,
            movie_rss=movie_rss,
            vault_movie=movie,
            user=user,
            tmdb_id=movie.tmdb_id,
        )

        final_status: ImportStatus = "created" if candidate is not None and movie.source == Movie.Source.TMDB else "reused"
        final_message = f"Фильм обработан и статус '{WONT_WATCH_LABEL}' выставлен"
        cls._log(
            operation_id=operation_id,
            level=VaultConnectionEvent.Level.SUCCESS,
            event_type="operation_completed",
            message=final_message,
            torrent_id=0,
            movie_rss=movie_rss,
            vault_movie=movie,
            user=user,
            tmdb_id=movie.tmdb_id,
        )
        return KinozalDownloadImportResult(
            operation_id=operation_id,
            status=final_status,
            message=final_message,
            movie=movie,
        )

    # ------------------------------------ #
    #            DOMAIN LAYER              #
    # ------------------------------------ #

    @classmethod
    def _find_existing_movie(
        cls,
        movie_rss: MovieRSS,
        *,
        operation_id: UUID,
        torrent_id: int,
        user,
    ) -> Movie | None:
        if movie_rss.imdb_id:
            movie = Movie.objects.filter(imdb_id=movie_rss.imdb_id).first()
            if movie is not None:
                cls._log(
                    operation_id=operation_id,
                    level=VaultConnectionEvent.Level.INFO,
                    event_type="vault_movie_reused_by_imdb",
                    message="Найден существующий фильм в Vault по IMDb ID",
                    movie_rss=movie_rss,
                    vault_movie=movie,
                    torrent_id=torrent_id,
                    user=user,
                    tmdb_id=movie.tmdb_id,
                )
                return movie

        if movie_rss.kinopoisk_id:
            movie = Movie.objects.filter(kinopoisk_id=movie_rss.kinopoisk_id).first()
            if movie is not None:
                cls._log(
                    operation_id=operation_id,
                    level=VaultConnectionEvent.Level.INFO,
                    event_type="vault_movie_reused_by_kinopoisk",
                    message="Найден существующий фильм в Vault по Kinopoisk ID",
                    movie_rss=movie_rss,
                    vault_movie=movie,
                    torrent_id=torrent_id,
                    user=user,
                    tmdb_id=movie.tmdb_id,
                )
                return movie

        return None

    @classmethod
    def _resolve_tmdb_match(
        cls,
        movie_rss: MovieRSS,
        *,
        operation_id: UUID,
        torrent_id: int,
        user,
    ) -> TMDBMatchingResult | None:
        if movie_rss.imdb_id:
            cls._log(
                operation_id=operation_id,
                level=VaultConnectionEvent.Level.INFO,
                event_type="tmdb_lookup_started",
                message=f"Старт TMDB lookup по IMDb ID {movie_rss.imdb_id}",
                movie_rss=movie_rss,
                torrent_id=torrent_id,
                user=user,
            )
            imdb_match = TMDBMovieMatchingService.find_by_imdb_id(
                movie_rss.imdb_id,
                expected_media_type="movie",
            )
            cls._log_match_result(
                operation_id=operation_id,
                event_type="tmdb_lookup_result_imdb",
                movie_rss=movie_rss,
                torrent_id=torrent_id,
                user=user,
                match_result=imdb_match,
            )
            if imdb_match.status == "auto_match":
                return imdb_match

            # IMDb ID есть — эвристики по названию/году не запускаем:
            # если TMDB не знает этот идентификатор, синк честно обрывается.
            if imdb_match.status == "not_found":
                return TMDBMatchingResult(
                    status="not_found",
                    selected_candidate=None,
                    candidates=tuple(),
                    message=TMDBMovieMatchingService.IMDB_NOT_ON_TMDB_MESSAGE,
                )
            return imdb_match

        year = cls._parse_year(movie_rss.year)
        probe_movie = Movie(
            title=movie_rss.title,
            original_title=movie_rss.original_title or "",
            year=year,
            movie_type=Movie.MovieType.MOVIE,
            imdb_id=movie_rss.imdb_id,
            kinopoisk_id=movie_rss.kinopoisk_id,
        )
        cls._log(
            operation_id=operation_id,
            level=VaultConnectionEvent.Level.INFO,
            event_type="tmdb_lookup_started_fallback",
            message="Старт fallback lookup по title/original_title/year",
            movie_rss=movie_rss,
            torrent_id=torrent_id,
            user=user,
            payload={"year": year},
        )
        fallback_match = TMDBMovieMatchingService.match_movie(probe_movie)
        cls._log_match_result(
            operation_id=operation_id,
            event_type="tmdb_lookup_result_fallback",
            movie_rss=movie_rss,
            torrent_id=torrent_id,
            user=user,
            match_result=fallback_match,
        )
        return fallback_match

    @classmethod
    def _log_match_result(
        cls,
        *,
        operation_id: UUID,
        event_type: str,
        movie_rss: MovieRSS,
        torrent_id: int,
        user,
        match_result: TMDBMatchingResult,
    ) -> None:
        first_candidate = match_result.candidates[0] if match_result.candidates else None
        level = VaultConnectionEvent.Level.INFO
        if match_result.status == "auto_match":
            level = VaultConnectionEvent.Level.SUCCESS
        elif match_result.status == "needs_user_choice":
            level = VaultConnectionEvent.Level.WARNING
        elif match_result.status == "not_found":
            level = VaultConnectionEvent.Level.ERROR

        cls._log(
            operation_id=operation_id,
            level=level,
            event_type=event_type,
            message=match_result.message,
            movie_rss=movie_rss,
            torrent_id=torrent_id,
            user=user,
            tmdb_id=first_candidate.tmdb_id if first_candidate is not None else None,
            payload={
                "status": match_result.status,
                "candidates": [
                    {
                        "tmdb_id": item.tmdb_id,
                        "media_type": item.media_type,
                        "title": item.title,
                        "year": item.year,
                        "score": item.score,
                    }
                    for item in match_result.candidates
                ],
            },
        )

    @classmethod
    def _persist_external_ids(cls, movie: Movie, movie_rss: MovieRSS) -> None:
        update_fields: list[str] = []
        if movie_rss.imdb_id and movie.imdb_id != movie_rss.imdb_id:
            movie.imdb_id = movie_rss.imdb_id
            update_fields.append("imdb_id")
        if movie_rss.kinopoisk_id and movie.kinopoisk_id != movie_rss.kinopoisk_id:
            movie.kinopoisk_id = movie_rss.kinopoisk_id
            update_fields.append("kinopoisk_id")
        if update_fields:
            movie.save(update_fields=update_fields)

    @staticmethod
    def _parse_year(value: str | None) -> int | None:
        raw = (value or "").strip()
        if not raw:
            return None
        primary = raw[:4]
        return int(primary) if primary.isdigit() else None

    @classmethod
    def _log(
        cls,
        *,
        operation_id: UUID,
        level: str,
        event_type: str,
        message: str,
        torrent_id: int,
        user,
        movie_rss: MovieRSS | None = None,
        vault_movie: Movie | None = None,
        tmdb_id: int | None = None,
        payload: dict | None = None,
    ) -> None:
        VaultConnectionEvent.objects.create(
            operation_id=operation_id,
            source=VaultConnectionEvent.Source.KINOZAL_DOWNLOAD,
            event_type=event_type,
            level=level,
            message=message,
            payload=payload,
            user=user if getattr(user, "is_authenticated", False) else None,
            movie_rss=movie_rss,
            vault_movie=vault_movie,
            rss_kinozal_id=movie_rss.kinozal_id if movie_rss is not None else None,
            torrent_kinozal_id=torrent_id,
            imdb_id=movie_rss.imdb_id if movie_rss is not None else None,
            kinopoisk_id=movie_rss.kinopoisk_id if movie_rss is not None else None,
            tmdb_id=tmdb_id or (vault_movie.tmdb_id if vault_movie is not None else None),
        )
