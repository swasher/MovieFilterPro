from __future__ import annotations

import logging
import traceback
from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from moviefilter.models import UserPreferences
from vault.models import Movie, TMDBSyncQueueItem
from vault.services.tmdb_movie_sync_service import TMDBSyncResult, TMDBMovieSyncService

logger = logging.getLogger("vault.tmdb_sync")


# ------------------------------------ #
#          APPLICATION LAYER          #
# ------------------------------------ #


class TMDBSyncQueueService:
    """Очередь массовой синхронизации локальной фильмотеки с TMDB.

    Элементы очереди (TMDBSyncQueueItem) создаются кнопкой «Добавить все»,
    обработку ведёт HUEY-тик tmdb_sync_tick по одному фильму за раз.
    """

    STATE_KEYS = ("pending", "in_progress", "synced", "confirm", "not_found", "error")

    # ------------------------------------------------------------------ #
    #                  Управление очередью (UI-кнопки)                    #
    # ------------------------------------------------------------------ #

    @classmethod
    def enqueue_unsynced(cls) -> dict:
        """Кнопка «Добавить все»: поставить в очередь все несинхронизированные фильмы."""
        target_qs = cls._unsynced_movies()
        already_queued = set(
            TMDBSyncQueueItem.objects.filter(movie__in=target_qs).values_list("movie_id", flat=True)
        )

        objects = []
        for movie in target_qs:
            if movie.id in already_queued:
                continue
            objects.append(
                TMDBSyncQueueItem(
                    movie_id=movie.id,
                    snapshot_title=movie.title or "",
                    snapshot_original_title=movie.original_title or "",
                    snapshot_year=movie.year,
                    snapshot_movie_type=movie.movie_type,
                    snapshot_imdb_id=movie.imdb_id or "",
                    snapshot_kinopoisk_id=movie.kinopoisk_id,
                )
            )

        if objects:
            TMDBSyncQueueItem.objects.bulk_create(objects, ignore_conflicts=True)

        added = len(objects)
        total_in_queue = TMDBSyncQueueItem.objects.count()
        logger.info(f"ENQUEUE_UNSYNCED | added={added} | total_in_queue={total_in_queue}")
        return {"added": added, "total": total_in_queue}

    @classmethod
    def enqueue_resync(cls) -> dict:
        """Кнопка «Re-Sync»: пересинхронизировать уже сопоставленные с TMDB фильмы.

        Сначала удаляются успешно завершённые записи очереди (чтобы у одного фильма
        не оказалось двух статусов), затем все фильмы с заполненным tmdb_id
        добавляются в очередь. Новые записи получают queued_at в прошлом,
        поэтому обрабатываются первыми.
        """
        removed = cls.remove_synced()

        target_qs = Movie.objects.filter(tmdb_id__isnull=False)
        already_queued = set(
            TMDBSyncQueueItem.objects.values_list("movie_id", flat=True)
        )

        objects = []
        for movie in target_qs:
            if movie.id in already_queued:
                continue
            objects.append(
                TMDBSyncQueueItem(
                    movie_id=movie.id,
                    snapshot_title=movie.title or "",
                    snapshot_original_title=movie.original_title or "",
                    snapshot_year=movie.year,
                    snapshot_movie_type=movie.movie_type,
                    snapshot_imdb_id=movie.imdb_id or "",
                    snapshot_kinopoisk_id=movie.kinopoisk_id,
                )
            )

        if objects:
            # queued_at имеет auto_now_add и перезапишется при bulk_create,
            # поэтому сдвигаем время в прошлое отдельным update().
            min_queued = TMDBSyncQueueItem.objects.order_by("queued_at").values_list(
                "queued_at", flat=True
            ).first()
            backdated = (
                (min_queued - timedelta(seconds=1))
                if min_queued is not None
                else timezone.now() - timedelta(hours=1)
            )
            TMDBSyncQueueItem.objects.bulk_create(objects, ignore_conflicts=True)
            TMDBSyncQueueItem.objects.filter(
                movie_id__in=[obj.movie_id for obj in objects]
            ).update(queued_at=backdated)

        added = len(objects)
        total_in_queue = TMDBSyncQueueItem.objects.count()
        logger.info(
            f"ENQUEUE_RESYNC | removed_synced={removed} | added={added} | total_in_queue={total_in_queue}"
        )
        return {"added": added, "removed": removed, "total": total_in_queue}

    @classmethod
    def start(cls) -> None:
        prefs = UserPreferences.get()
        if not prefs.tmdb_sync_enabled:
            prefs.tmdb_sync_enabled = True
            prefs.save(update_fields=["tmdb_sync_enabled"])
        # R3/R4: прогрев dict-кэша списков + создание недостающих TMDB-листов заранее.
        # WEB-прогрев (один SELECT) — дёшево; воркер прогреется лениво в sync_list_item_added
        # или фоновой задачей tmdb_lists_init (та же память воркера, но отдельный таск — страховка).
        try:
            from vault.services.tmdb_writeback_service import warm_user_list_id_cache

            warm_user_list_id_cache()
        except Exception:
            pass
        try:
            from vault.tasks import tmdb_lists_init

            tmdb_lists_init.schedule(delay=2)
        except Exception as exc:
            logger.warning(f"TMDB_SYNC_START lists_init schedule failed: {exc}")
        cls._schedule_tick(delay=1)

    @classmethod
    def stop(cls) -> None:
        prefs = UserPreferences.get()
        if not prefs.tmdb_sync_enabled:
            return
        prefs.tmdb_sync_enabled = False
        prefs.save(update_fields=["tmdb_sync_enabled"])
        logger.info("TMDB_SYNC_STOP")

    @classmethod
    def remove_all(cls) -> int:
        """Удалить все записи очереди и остановить обработку."""
        with transaction.atomic():
            removed, _ = TMDBSyncQueueItem.objects.all().delete()
            cls.stop()
        logger.info(f"TMDB_SYNC_REMOVE_ALL | removed={removed}")
        return removed

    @classmethod
    def remove_synced(cls) -> int:
        """Удалить только успешно синхронизированные записи очереди."""
        with transaction.atomic():
            removed, _ = TMDBSyncQueueItem.objects.filter(
                state=TMDBSyncQueueItem.State.SYNCED
            ).delete()
        logger.info(f"TMDB_SYNC_REMOVE_SYNCED | removed={removed}")
        return removed

    @classmethod
    def remove_item(cls, item_id: int) -> TMDBSyncQueueItem | None:
        """Удалить одну запись очереди (без остановки обработки)."""
        item = TMDBSyncQueueItem.objects.filter(pk=item_id).first()
        if item is None:
            return None
        if item.state == TMDBSyncQueueItem.State.IN_PROGRESS:
            raise ValueError("Нельзя удалить элемент, который сейчас синхронизируется")
        item.delete()
        logger.info(f"TMDB_SYNC_REMOVE_ITEM | item_id={item_id}")
        return item

    @classmethod
    def set_delay(cls, seconds: int) -> int:
        seconds = int(seconds)
        if not 1 <= seconds <= 3600:
            raise ValueError("delay_seconds должен быть в диапазоне 1..3600")
        prefs = UserPreferences.get()
        prefs.tmdb_sync_delay_seconds = seconds
        prefs.save(update_fields=["tmdb_sync_delay_seconds"])
        return seconds

    @classmethod
    def get_state(cls) -> dict:
        prefs = UserPreferences.get()
        counters = {key: 0 for key in cls.STATE_KEYS}
        for row in TMDBSyncQueueItem.objects.values("state").annotate(row_count=Count("id")):
            counters[row["state"]] = row["row_count"]

        return {
            "enabled": prefs.tmdb_sync_enabled,
            "delay_seconds": prefs.tmdb_sync_delay_seconds,
            "counters": counters,
            "total_unsynced": cls._unsynced_count(),
        }

    # ------------------------------------------------------------------ #
    #                   Исполнитель (вызов из HUEY-тика)                  #
    # ------------------------------------------------------------------ #

    @classmethod
    def process_one(cls) -> dict | None:
        """Обработать один PENDING-фильм. Возвращает словарь результата или None."""
        prefs = UserPreferences.get()
        if not prefs.tmdb_sync_enabled:
            return None

        item = cls._next_pending_item()
        if item is None:
            return None

        try:
            movie = Movie.objects.get(pk=item.movie_id)
        except Movie.DoesNotExist:
            item.state = TMDBSyncQueueItem.State.ERROR
            item.finished_at = timezone.now()
            item.result_status = "error"
            item.result_message = "Фильм был удалён до начала синхронизации"
            item.save(update_fields=["state", "finished_at", "result_status", "result_message"])
            return {"state": item.state, "movie_id": item.movie_id}

        outcome = cls._run_sync(item, movie)

        item.finished_at = timezone.now()
        cls._apply_outcome(item, outcome, movie)
        item.save()

        logger.info(
            f'TICK_DONE | movie_id={movie.id} | title="{movie.title}" '
            f'| state={item.state} | msg="{item.result_message}"'
        )

        # Само-перепланирование следующего тика
        if (
            prefs.tmdb_sync_enabled
            and TMDBSyncQueueItem.objects.filter(state=TMDBSyncQueueItem.State.PENDING).exists()
        ):
            cls._schedule_tick(delay=prefs.tmdb_sync_delay_seconds)

        return {
            "state": item.state,
            "movie_id": movie.id,
            "result_tmdb_id": item.result_tmdb_id,
            "result_media_type": item.result_media_type,
            "result_message": item.result_message,
        }

    @classmethod
    def _run_sync(cls, item: TMDBSyncQueueItem, movie: Movie) -> dict:
        try:
            result: TMDBSyncResult = TMDBMovieSyncService.sync_movie(movie=movie)
        except Exception as exc:
            return {
                "state": TMDBSyncQueueItem.State.ERROR,
                "result_status": "error",
                "result_message": f"Исключение: {exc}",
                "error_trace": traceback.format_exc(),
            }

        if result.status == "ok":
            return {
                "state": TMDBSyncQueueItem.State.SYNCED,
                "result": result,
            }

        if result.status in {"needs_confirmation", "needs_user_choice"}:
            candidates_text = cls._candidates_text(result)
            message = result.message or ""
            if candidates_text:
                message = f"{message} | {candidates_text}" if message else candidates_text
            return {
                "state": TMDBSyncQueueItem.State.CONFIRM,
                "result_status": result.status,
                "result_message": message,
                "candidates_text": candidates_text,
            }

        # not_found / прочие «error» из сопоставления
        return {
            "state": TMDBSyncQueueItem.State.NOT_FOUND
            if "не найден" in (result.message or "").lower()
            else TMDBSyncQueueItem.State.ERROR,
            "result_status": "error",
            "result_message": result.message or "Ошибка синхронизации",
        }

    @classmethod
    def _apply_outcome(cls, item: TMDBSyncQueueItem, outcome: dict, movie: Movie) -> None:
        item.state = outcome["state"]
        item.result_status = outcome.get("result_status", "")
        item.result_message = outcome.get("result_message", "") or ""

        result = outcome.get("result")
        if isinstance(result, TMDBSyncResult) and result.status == "ok":
            candidate = result.selected_candidate
            if candidate is not None:
                item.result_tmdb_id = candidate.tmdb_id
                item.result_media_type = candidate.media_type
            else:
                item.result_tmdb_id = movie.tmdb_id
                item.result_media_type = movie.tmdb_media_type
            item.result_title = movie.title or ""
            item.result_original_title = movie.original_title or ""
            item.result_year = movie.year

        item.error_trace = outcome.get("error_trace", "")

    @classmethod
    def _next_pending_item(cls) -> TMDBSyncQueueItem | None:
        # Не обрабатываем, если другой тик уже взял элемент (защита -w 2 и повторных тиков).
        if TMDBSyncQueueItem.objects.filter(state=TMDBSyncQueueItem.State.IN_PROGRESS).exists():
            return None

        qs = (
            TMDBSyncQueueItem.objects.filter(state=TMDBSyncQueueItem.State.PENDING)
            .select_related("movie")
            .order_by("queued_at", "id")
        )
        with transaction.atomic():
            item = qs.select_for_update(skip_locked=True).first()
            if item is None:
                return None
            cls._mark_started(item)
        return item

    @classmethod
    def _mark_started(cls, item: TMDBSyncQueueItem) -> None:
        item.state = TMDBSyncQueueItem.State.IN_PROGRESS
        item.started_at = timezone.now()
        item.save(update_fields=["state", "started_at"])

    # ------------------------------------------------------------------ #
    #                    Watchdog / вспомогательное                       #
    # ------------------------------------------------------------------ #

    @classmethod
    def watchdog_run(cls) -> bool:
        """Периодическая подстраховка: тик давно не перепланирован — подтолкнуть."""
        if not UserPreferences.get().tmdb_sync_enabled:
            return False
        if not TMDBSyncQueueItem.objects.filter(state=TMDBSyncQueueItem.State.PENDING).exists():
            return False
        if TMDBSyncQueueItem.objects.filter(state=TMDBSyncQueueItem.State.IN_PROGRESS).exists():
            return False
        cls._schedule_tick(delay=1)
        logger.info("TMDB_SYNC_WATCHDOG | tick rescheduled")
        return True

    @classmethod
    def _schedule_tick(cls, delay: int) -> None:
        from vault.tasks import tmdb_sync_tick

        try:
            tmdb_sync_tick.schedule(delay=delay)
        except Exception as exc:  # воркер может быть не запущен — не роняем API
            logger.warning(f"TMDB_SYNC_SCHEDULE_FAILED | delay={delay} | {exc}")

    @classmethod
    def _unsynced_movies(cls):
        return Movie.objects.filter(source=Movie.Source.KINORIUM, tmdb_id__isnull=True)

    @classmethod
    def _unsynced_count(cls) -> int:
        return cls._unsynced_movies().count()

    @staticmethod
    def _candidates_text(result: TMDBSyncResult) -> str:
        parts = []
        for cand in result.candidates or ():
            parts.append(
                f"{cand.tmdb_id}|{cand.media_type}|{cand.title}"
                f"{' (' + str(cand.original_title) + ')' if cand.original_title else ''}"
                f" ({cand.year or '?'}) score={cand.score}"
            )
        return "; ".join(parts)