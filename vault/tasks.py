from __future__ import annotations

from uuid import UUID

from django.contrib.auth import get_user_model

from movie_filter_pro.huey import HUEY
from moviefilter.models import MovieRSS
from vault.services.kinozal_download_import_service import KinozalDownloadImportService


@HUEY.task()
def process_kinozal_download_import(
    operation_id: str,
    movie_rss_id: int,
    torrent_id: int,
    user_id: int | None,
    saved_to: str,
):
    operation_uuid = UUID(operation_id)
    user = None
    if user_id is not None:
        user = get_user_model().objects.filter(pk=user_id).first()

    try:
        result = KinozalDownloadImportService.handle_successful_download(
            movie_rss_id=movie_rss_id,
            torrent_id=torrent_id,
            user=user,
            saved_to=saved_to,
            operation_id=operation_uuid,
            log_download_saved=False,
        )
        return {
            "operation_id": str(result.operation_id),
            "status": result.status,
            "message": result.message,
            "movie_id": result.movie.id if result.movie is not None else None,
        }
    except Exception as exc:
        movie_rss = MovieRSS.objects.filter(pk=movie_rss_id).first()
        KinozalDownloadImportService._log(
            operation_id=operation_uuid,
            level="error",
            event_type="background_import_failed",
            message=f"Фоновая обработка завершилась ошибкой: {exc}",
            torrent_id=torrent_id,
            user=user,
            movie_rss=movie_rss,
            payload={"error_type": type(exc).__name__},
        )
        raise


@HUEY.task()
def process_kinozal_hide_action(
    operation_id: str,
    movie_rss_id: int,
    user_id: int | None,
):
    operation_uuid = UUID(operation_id)
    user = None
    if user_id is not None:
        user = get_user_model().objects.filter(pk=user_id).first()

    try:
        result = KinozalDownloadImportService.handle_hide_action(
            movie_rss_id=movie_rss_id,
            user=user,
            operation_id=operation_uuid,
        )
        return {
            "operation_id": str(result.operation_id),
            "status": result.status,
            "message": result.message,
            "movie_id": result.movie.id if result.movie is not None else None,
        }
    except Exception as exc:
        movie_rss = MovieRSS.objects.filter(pk=movie_rss_id).first()
        KinozalDownloadImportService._log(
            operation_id=operation_uuid,
            level="error",
            event_type="background_import_failed",
            message=f"Фоновая hide-обработка завершилась ошибкой: {exc}",
            torrent_id=0,
            user=user,
            movie_rss=movie_rss,
            payload={"error_type": type(exc).__name__},
        )
        raise
