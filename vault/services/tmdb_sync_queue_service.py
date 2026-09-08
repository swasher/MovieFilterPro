from __future__ import annotations

import logging
import traceback
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from moviefilter.models import UserPreferences
from vault.models import Movie, TMDBSyncQueueItem
from vault.services.tmdb_movie_sync_service import TMDBSyncResult, TMDBMovieSyncService

logger = logging.getLogger("vault.tmdb_sync")


class TMDBSyncKeysMissingError(ValueError):
    """Очередь TMDB sync нельзя стартовать: не настроены API-ключи."""

    def __init__(self, missing_keys: list[str]):
        self.missing_keys = list(missing_keys)
        labels = [TMDBSyncQueueService.KEY_LABELS.get(k, k) for k in missing_keys]
        super().__init__(
            "TMDB sync нельзя запустить: не настроены ключи: "
            + ", ".join(labels)
            + ". Заполни их в Preferences."
        )


# ------------------------------------ #
#          APPLICATION LAYER          #
# ------------------------------------ #


class TMDBSyncQueueService:
    """Очередь массовой синхронизации локальной фильмотеки с TMDB.

    Элементы очереди (TMDBSyncQueueItem) создаются кнопкой «Добавить все»,
    обработку ведёт HUEY-тик tmdb_sync_tick по одному фильму за раз.
    """

    STATE_KEYS = ("pending", "in_progress", "synced", "confirm", "not_found", "error")

    # IN_PROGRESS старше этого возраста считается оборванным тиком
    # (воркер упал/перезапустился/Huey потерял задачу) и возвращается в PENDING.
    # Обычный синк даже жирного сериала укладывается в единицы минут.
    STALE_IN_PROGRESS_TIMEOUT = timedelta(minutes=20)

    # Ключи, без которых очередь нельзя стартовать:
    # tmdb_api_key — сам TMDB sync, omdb_api_key — рейтинги IMDb/RT/Metacritic
    # (OMDB тянется внутри каждого синка по imdb_id).
    REQUIRED_KEY_FIELDS = ("tmdb_api_key", "omdb_api_key")
    KEY_LABELS = {
        "tmdb_api_key": "TMDB API key",
        "omdb_api_key": "OMDB API key",
    }

    @classmethod
    def get_missing_keys(cls, prefs=None) -> list[str]:
        """Список незаполненных API-ключей, нужных для TMDB sync.

        OMDB считается настроенным, если ключ есть хотя бы где-то
        (UserPreferences.omdb_api_key или legacy OMDB_API_KEY в .env),
        т.к. OMDBService умеет оба источника.
        """
        from vault.services.omdb_service import OMDBService

        prefs = prefs if prefs is not None else UserPreferences.get()
        missing: list[str] = []
        if not (prefs.tmdb_api_key or "").strip():
            missing.append("tmdb_api_key")
        if not OMDBService.is_configured():
            missing.append("omdb_api_key")
        return missing

    # ТЗ 6d: стоп-кран — 3 подряд фейла, bulk_stats каждые 100
    _consecutive_failures: int = 0
    _bulk_stats: dict[str, int] = {
        "success": 0,
        "not_found": 0,
        "confirm": 0,
        "error": 0,
        "rate_limited": 0,
        "critical": 0,
    }
    _last_errors: list[str] = []
    _processed_count: int = 0

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
        missing = cls.get_missing_keys(prefs)
        if missing:
            raise TMDBSyncKeysMissingError(missing)
        if not prefs.tmdb_sync_enabled:
            prefs.tmdb_sync_enabled = True
            prefs.save(update_fields=["tmdb_sync_enabled"])
        # ТЗ 6d: сброс стоп-крана и статистики bulk
        cls._consecutive_failures = 0
        cls._last_errors = []
        cls._processed_count = 0
        cls._bulk_stats = {k: 0 for k in cls._bulk_stats}
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
    def get_state(cls) -> dict:
        prefs = UserPreferences.get()
        counters = {key: 0 for key in cls.STATE_KEYS}
        for row in TMDBSyncQueueItem.objects.values("state").annotate(row_count=Count("id")):
            counters[row["state"]] = row["row_count"]

        return {
            "enabled": prefs.tmdb_sync_enabled,
            "counters": counters,
            "total_unsynced": cls._unsynced_count(),
            "missing_keys": cls.get_missing_keys(prefs),
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

        missing = cls.get_missing_keys(prefs)
        if missing:
            labels = [cls.KEY_LABELS.get(k, k) for k in missing]
            logger.critical(
                "TMDB_SYNC_STOP | reason=missing_keys | missing=%s", ",".join(missing)
            )
            cls.stop()
            return {
                "state": "stopped",
                "movie_id": None,
                "result_message": "Очередь остановлена: не настроены ключи: "
                + ", ".join(labels)
                + ". Заполни их в Preferences.",
            }

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

        logger.info(
            f'TICK_START | item_id={item.id} | movie_id={movie.id} | title="{movie.title}"'
        )
        outcome = cls._run_sync(item, movie)

        item.finished_at = timezone.now()
        cls._apply_outcome(item, outcome, movie)
        item.save()

        logger.info(
            f'TICK_DONE | movie_id={movie.id} | title="{movie.title}" '
            f'| state={item.state} | msg="{item.result_message}"'
        )

        # ТЗ 6d: bulk_stats + стоп-кран 3 подряд + лог каждые 100
        cls._processed_count += 1
        cls._update_bulk_stats(item.state, outcome)
        if cls._is_critical_outcome(outcome):
            cls._bulk_stats["critical"] = cls._bulk_stats.get("critical", 0) + 1
            cls._last_errors.append(f"critical movie={movie.id} msg={item.result_message[:200]}")
            cls._last_errors = cls._last_errors[-5:]
            logger.critical("BULK_STOP | reason=critical_401 | movie=%s msg=%s", movie.id, item.result_message[:300])
            cls.stop()
            # стоп обеих очередей: writeback тоже
            try:
                from moviefilter.models import UserPreferences as _UP

                # writeback критичный уже в ERROR без ретрая, но на всякий — лог
                logger.critical("BULK_STOP | writeback also stopped due to critical auth")
            except Exception:
                pass
            return {
                "state": item.state,
                "movie_id": movie.id,
                "result_message": item.result_message,
                "bulk_stopped": "critical",
            }
        if item.state == TMDBSyncQueueItem.State.ERROR:
            # считаем только транзиентные/лимит как фейл для подряд (бизнес NOT_FOUND/CONFIRM уже не ERROR)
            is_rate = "429" in (item.result_message or "") or "Rate limit" in (item.result_message or "")
            cls._consecutive_failures += 1
            cls._last_errors.append(f"movie={movie.id} err={item.result_message[:200]}")
            cls._last_errors = cls._last_errors[-5:]
            if is_rate:
                cls._bulk_stats["rate_limited"] += 1
            if cls._consecutive_failures >= 3:
                logger.critical("BULK_STOP | reason=3_consecutive_failures | last_errors=%s", cls._last_errors)
                cls.stop()
                return {
                    "state": item.state,
                    "movie_id": movie.id,
                    "result_message": item.result_message,
                    "bulk_stopped": "consecutive",
                }
        else:
            # SYNCED, NOT_FOUND, CONFIRM — сброс подряд
            cls._consecutive_failures = 0

        if cls._processed_count % 100 == 0:
            total_pending = TMDBSyncQueueItem.objects.filter(state=TMDBSyncQueueItem.State.PENDING).count()
            logger.info(
                "BULK_PROGRESS | done=%s | pending=%s | success=%s not_found=%s confirm=%s error=%s rate=%s critical=%s",
                cls._processed_count,
                total_pending,
                cls._bulk_stats.get("success", 0),
                cls._bulk_stats.get("not_found", 0),
                cls._bulk_stats.get("confirm", 0),
                cls._bulk_stats.get("error", 0),
                cls._bulk_stats.get("rate_limited", 0),
                cls._bulk_stats.get("critical", 0),
            )

        # После успешной pull-синхронизации — залить локальные статусы/списки обратно в TMDB (writeback)
        # Bulk-импорт 10K: у каждого фильма может быть UserMovie с watch_status/rating/favorite + списки.
        # Раньше pull не триггерил push, поэтому tmdb-writeback не выполнялся.
        if item.state == TMDBSyncQueueItem.State.SYNCED:
            try:
                from vault.models import UserMovie as _UM
                from vault.services.tmdb_writeback_dispatch import TmdbWritebackDispatch

                # Берём свежий movie с tmdb_id, т.к. movie уже сохранён выше
                fresh_movie = Movie.objects.filter(pk=movie.pk).first()
                if fresh_movie and fresh_movie.tmdb_id:
                    for um in _UM.objects.filter(movie=fresh_movie).only("id"):
                        # Full sync (None) — списки тоже пройдут через sync_list_item_added
                        TmdbWritebackDispatch.schedule_user_movie_writeback(um.pk, changed_fields=None)
            except Exception as exc:
                logger.warning("writeback schedule after sync failed movie=%s: %s", movie.id, exc)

        # Само-перепланирование следующего тика (проверяем enabled ещё раз после возможного stop)
        # Лимитер 0.5 сек уже душит TMDB, дополнительный ручной темп не нужен — фиксированно 1 сек
        prefs = UserPreferences.get()
        if (
            prefs.tmdb_sync_enabled
            and TMDBSyncQueueItem.objects.filter(state=TMDBSyncQueueItem.State.PENDING).exists()
        ):
            cls._schedule_tick(delay=1)

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
    def _update_bulk_stats(cls, state: str, outcome: dict) -> None:
        if state == TMDBSyncQueueItem.State.SYNCED:
            cls._bulk_stats["success"] = cls._bulk_stats.get("success", 0) + 1
        elif state == TMDBSyncQueueItem.State.NOT_FOUND:
            cls._bulk_stats["not_found"] = cls._bulk_stats.get("not_found", 0) + 1
        elif state == TMDBSyncQueueItem.State.CONFIRM:
            cls._bulk_stats["confirm"] = cls._bulk_stats.get("confirm", 0) + 1
        elif state == TMDBSyncQueueItem.State.ERROR:
            cls._bulk_stats["error"] = cls._bulk_stats.get("error", 0) + 1

    @classmethod
    def _is_critical_outcome(cls, outcome: dict) -> bool:
        msg = (outcome.get("result_message") or "") + " " + (outcome.get("error_trace") or "")
        # 401 критичная — как в writeback
        return (
            "401" in msg
            or "Invalid API key" in msg
            or "Authentication" in msg
            or "Unauthorized" in msg
            or "WritePermission" in msg
            or "PrivateResource" in msg
        )

    @classmethod
    def _next_pending_item(cls) -> TMDBSyncQueueItem | None:
        # Сначала реанимируем оборванные тики, иначе один залипший IN_PROGRESS
        # навсегда останавливает очередь (и тики, и watchdog отказываются работать).
        cls._reclaim_stale_in_progress()

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
        if cls.get_missing_keys():
            # Ключи снесли на ходу — глушим очередь, а не дёргаем тики впустую.
            cls.stop()
            return False
        # Реанимация оборванных тиков — иначе очередь мертва навсегда.
        cls._reclaim_stale_in_progress()
        if not TMDBSyncQueueItem.objects.filter(state=TMDBSyncQueueItem.State.PENDING).exists():
            return False
        if TMDBSyncQueueItem.objects.filter(state=TMDBSyncQueueItem.State.IN_PROGRESS).exists():
            return False
        cls._schedule_tick(delay=1)
        logger.info("TMDB_SYNC_WATCHDOG | tick rescheduled")
        return True

    @classmethod
    def _reclaim_stale_in_progress(cls) -> int:
        """Вернуть оборванные IN_PROGRESS обратно в PENDING.

        IN_PROGRESS старше STALE_IN_PROGRESS_TIMEOUT — это тик, который уже
        никогда не завершится (воркер упал/перезапустился, Huey потерял задачу,
        сеть повисла без таймаута). Возвращаем в очередь с инкрементом попыток.
        """
        cutoff = timezone.now() - cls.STALE_IN_PROGRESS_TIMEOUT
        stale_qs = TMDBSyncQueueItem.objects.filter(
            state=TMDBSyncQueueItem.State.IN_PROGRESS
        ).filter(Q(started_at__lt=cutoff) | Q(started_at__isnull=True))
        reclaimed = 0
        for item in stale_qs:
            item.state = TMDBSyncQueueItem.State.PENDING
            item.started_at = None
            item.retry_count = (item.retry_count or 0) + 1
            item.result_message = (
                "Тик оборвался (stale IN_PROGRESS), возвращено в очередь. "
                f"Попытка №{item.retry_count}."
            )
            item.save(update_fields=["state", "started_at", "retry_count", "result_message"])
            reclaimed += 1
        if reclaimed:
            logger.warning("TMDB_SYNC_RECLAIM_STALE | reclaimed=%s", reclaimed)
        return reclaimed

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
            reasons = ",".join(cand.score_reasons or ())
            parts.append(
                f"{cand.tmdb_id}|{cand.media_type}|{cand.title}"
                f"{' (' + str(cand.original_title) + ')' if cand.original_title else ''}"
                f" ({cand.year or '?'}) score={cand.score} reasons=[{reasons}]"
            )
        return "; ".join(parts)