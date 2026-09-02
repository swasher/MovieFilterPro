from __future__ import annotations

from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from huey import crontab

from movie_filter_pro.huey import HUEY
from moviefilter.models import MovieRSS
from vault.services.kinozal_download_import_service import KinozalDownloadImportService
from vault.services.tmdb_sync_queue_service import TMDBSyncQueueService


@HUEY.task()
def tmdb_sync_tick():
    """Один такт массовой синхронизации: обрабатывает один фильм и
    само-перепланирует следующий тик через delay_seconds."""
    close_old_connections()
    return TMDBSyncQueueService.process_one()


@HUEY.periodic_task(crontab(minute="*/1"))
def tmdb_sync_watchdog():
    """Подстраховка: раз в минуту перезапускает цепочку тиков,
    если она заглохла (например, после рестарта воркера)."""
    close_old_connections()
    return TMDBSyncQueueService.watchdog_run()


@HUEY.task()
def process_kinozal_download_import(
    operation_id: str,
    movie_rss_id: int,
    torrent_id: int,
    user_id: int | None,
    saved_to: str,
):
    close_old_connections()
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
def tmdb_writeback_user_movie(user_movie_id: int, changed_fields: list[str] | None = None):
    """Фоновая write-back синхронизация одного UserMovie (статус/избранное/рейтинг).

    R1 Δ-sync: `changed_fields` — union накопленных изменений, None = full sync.
    """
    close_old_connections()
    from vault.services.tmdb_writeback_service import TmdbWritebackService

    return TmdbWritebackService.sync_user_movie_to_tmdb_by_id(user_movie_id, changed_fields=changed_fields)


@HUEY.task()
def tmdb_writeback_user_movie_delete(movie_id: int, tmdb_id, media_type):
    """Фоновая очистка write-back при удалении UserMovie (снапшот tmdb_id/media_type)."""
    close_old_connections()
    from vault.services.tmdb_writeback_service import TmdbWritebackService

    # Лёгкий снапшот как в старых сигналах — метод принимает объект с .movie
    class _MovieSnap:
        def __init__(self, id_, tid, mt):
            self.id = id_
            self.tmdb_id = tid
            self.tmdb_media_type = mt

    class _UMSnap:
        def __init__(self, pk_, movie):
            self.pk = pk_
            self.movie = movie

    snap = _UMSnap(movie_id, _MovieSnap(movie_id, tmdb_id, media_type))
    return TmdbWritebackService.sync_user_movie_deleted(snap)


@HUEY.task()
def tmdb_writeback_list_item_added(user_list_movie_id: int):
    """Фоновая запись: фильм добавлен в локальный список → в TMDB list."""
    close_old_connections()
    from vault.models import UserListMovie
    from vault.services.tmdb_writeback_service import TmdbWritebackService

    try:
        obj = UserListMovie.objects.select_related("user_list", "movie").get(pk=user_list_movie_id)
    except UserListMovie.DoesNotExist:
        return None
    return TmdbWritebackService.sync_list_item_added(obj)


@HUEY.task()
def tmdb_writeback_list_item_removed(tmdb_list_id, tmdb_id, media_type):
    """Фоновая запись: фильм удалён из локального списка → из TMDB list."""
    close_old_connections()
    from vault.services.tmdb_writeback_service import TmdbWritebackService

    # Снапшот для sync_list_item_removed (в post_delete объекта уже нет).
    class _ListSnap:
        def __init__(self, lid):
            self.id = 0
            self.tmdb_list_id = lid

    class _MovieSnap:
        def __init__(self, tid, mt):
            self.id = 0
            self.tmdb_id = tid
            self.tmdb_media_type = mt

    class _ListMovieSnap:
        def __init__(self, lst, mv):
            self.pk = 0
            self.user_list = lst
            self.movie = mv

    return TmdbWritebackService.sync_list_item_removed(
        _ListMovieSnap(_ListSnap(tmdb_list_id), _MovieSnap(tmdb_id, media_type))
    )


@HUEY.task()
def tmdb_writeback_list_sync(user_list_id: int):
    """Фоновая запись: локальный список создан/переименован → создать/обновить TMDB list."""
    close_old_connections()
    from vault.models import UserList
    from vault.services.tmdb_writeback_service import TmdbWritebackService

    try:
        ul = UserList.objects.get(pk=user_list_id)
    except UserList.DoesNotExist:
        return None
    if not ul.tmdb_list_id:
        return TmdbWritebackService.create_tmdb_list(ul)
    return TmdbWritebackService.update_tmdb_list(ul)


@HUEY.task()
def tmdb_writeback_list_delete(tmdb_list_id):
    """Фоновая запись: локальный список удалён → delete TMDB list."""
    close_old_connections()
    from vault.services.tmdb_writeback_service import TmdbWritebackService

    class _Snap:
        tmdb_list_id = tmdb_list_id
        id = 0

    return TmdbWritebackService.delete_tmdb_list(_Snap())


@HUEY.periodic_task(crontab(minute="*/10"))
def tmdb_writeback_retry_tick():
    """Forever queue: каждые 10м ретрает pending write-back (до success)."""
    close_old_connections()
    from django.utils import timezone
    from vault.models import TMDBWritebackQueueItem

    now = timezone.now()
    qs = TMDBWritebackQueueItem.objects.filter(next_retry_at__lte=now, state="pending").select_related("movie")[:20]
    retried = 0
    for item in qs:
        try:
            from vault.models import UserMovie

            um = UserMovie.objects.filter(movie=item.movie).first()
            if not um:
                # если UserMovie удалён — чистим очередь (delete уже успешна или не нужна)
                item.delete()
                continue
            from vault.services.tmdb_writeback_service import TmdbWritebackService

            TmdbWritebackService.sync_user_movie_to_tmdb(um)
            retried += 1
        except Exception:
            continue
    return {"retried": retried}





@HUEY.task()
@HUEY.lock_task("tmdb_lists_init")
def tmdb_lists_init():
    """Одноразовая инициализация всех локальных UserList на TMDB.

    lock_task — статический глобальный лок: не даёт двум запускам
    (например, повторный auth-approve) параллельно создавать дубликаты
    списков на TMDB. Здесь статический лок уместен — задача глобальная,
    а не per-argument.

    """
    close_old_connections()
    from vault.services.tmdb_writeback_service import TmdbWritebackService

    return TmdbWritebackService.init_all_user_lists()


@HUEY.task()
def process_kinozal_hide_action(
    operation_id: str,
    movie_rss_id: int,
    user_id: int | None,
):
    close_old_connections()
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
