"""
Диспетчер write-back операций Vault → TMDB.

Единственная точка, через которую сигналы ставят write-back в HUEY-очередь.
Выполнение происходит в воркере (задачи в vault/tasks.py), поэтому UI не
блокируется HTTP-вызовами к TMDB.

Дедупликация: одинаковые операции (например, несколько быстрых переключений
статуса одного UserMovie) схлопываются через `Result.reschedule()` — старый
scheduled-таск отзывается, вместо него ставится новый с теми же аргументами
и свежим delay. Выполнится только последняя версия.
"""
from __future__ import annotations

import logging
import time

from vault.constants import SKIP_LIST_NAME as _SKIP_LIST_NAME

logger = logging.getLogger("vault.tmdb_writeback")

# Задержка перед выполнением write-back. Окно для дедупликации: быстрые повторные
# сигналы по одному объекту заменяют предыдущий scheduled-таск.
WRITEBACK_DELAY_SECONDS = 2


class TmdbWritebackDispatch:
    """Ставит write-back задачи в HUEY с дедупликацией по ключу."""

    # Локальный системный зеркальный список "Не интересует" зеркально
    # синхронизируется в TMDB-лист с таким же именем.
    SKIP_LIST_NAME = _SKIP_LIST_NAME

    # Последний Result для каждого ключа дедупликации → reschedule() при повторе.
    _pending: dict[str, object] = {}
    # R1: накопленные changed_fields для union-дедупликации UserMovie
    _pending_changed: dict[str, set[str] | None] = {}
    _pending_ts: dict[str, float] = {}

    @classmethod
    def _schedule(cls, task, key: str, args: tuple, delay: int = WRITEBACK_DELAY_SECONDS):
        """Поставить таск с дедупликацией: отозвать предыдущую и поставить заново."""
        try:
            pending = cls._pending.get(key)
            if pending is not None:
                # reschedule() отзывает старый scheduled-таск и ставит новый
                # с теми же args + свежим delay; выполнится последняя версия.
                cls._pending[key] = pending.reschedule(delay=delay)
                return
        except Exception as exc:
            logger.warning("writeback dedup reschedule failed key=%s: %s", key, exc)

        try:
            cls._pending[key] = task.schedule(args=args, delay=delay)
        except Exception as exc:
            logger.warning("writeback schedule failed key=%s: %s", key, exc)

    # ------------------------------------------------------------------ #
    #                    Публичные API для сигналов                        #
    # ------------------------------------------------------------------ #

    @classmethod
    def schedule_user_movie_writeback(cls, user_movie_id: int, changed_fields: list[str] | None = None) -> None:
        """UserMovie сохранён → синхронизировать статус/избранное/рейтинг.

        R1 Δ-sync: `changed_fields` — список реально изменённых полей
        (watch_status/is_favorite/rating). None = полный sync (fallback).
        Union-дедупликация в окне WRITEBACK_DELAY_SECONDS.
        """
        from vault.tasks import tmdb_writeback_user_movie

        key = f"um:{user_movie_id}"
        # нормализация: None = full, [] не шедулим (сигнал уже отфильтровал)
        normalized: set[str] | None
        if changed_fields is None:
            normalized = None
        else:
            # пустой список — нечего делать, но на всякий — трактуем как no-op
            if not changed_fields:
                return
            normalized = set(changed_fields)

        now = time.monotonic()
        pending = cls._pending.get(key)
        pending_changed = cls._pending_changed.get(key)
        pending_ts = cls._pending_ts.get(key, 0)

        # Если pending старше окна — считаем что таск уже исполнился, не union'им
        is_stale = pending is not None and (now - pending_ts) > (WRITEBACK_DELAY_SECONDS + 0.5)

        if pending is not None and not is_stale:
            # union логика
            if pending_changed is None or normalized is None:
                merged: set[str] | None = None  # full
            else:
                merged = pending_changed | normalized
                # если merged не добавил новых полей — просто продлеваем delay
                if merged == pending_changed:
                    try:
                        cls._pending[key] = pending.reschedule(delay=WRITEBACK_DELAY_SECONDS)
                        cls._pending_ts[key] = now
                        return
                    except Exception as exc:
                        logger.warning("writeback dedup reschedule failed key=%s: %s", key, exc)
                        # fallback — пересоздадим ниже
            # need merged args → revoke old + schedule new
            try:
                pending.revoke()
            except Exception as exc:
                logger.warning("writeback revoke failed key=%s: %s", key, exc)
            # подготовить args для новой таски
            if merged is None:
                args = (user_movie_id, None)
            else:
                args = (user_movie_id, sorted(merged))
            try:
                cls._pending[key] = tmdb_writeback_user_movie.schedule(args=args, delay=WRITEBACK_DELAY_SECONDS)
                cls._pending_changed[key] = merged
                cls._pending_ts[key] = now
                return
            except Exception as exc:
                logger.warning("writeback schedule merged failed key=%s: %s", key, exc)
                return

        # нет pending или stale — новый schedule
        if normalized is None:
            args = (user_movie_id, None)
        else:
            args = (user_movie_id, sorted(normalized))
        try:
            cls._pending[key] = tmdb_writeback_user_movie.schedule(args=args, delay=WRITEBACK_DELAY_SECONDS)
            cls._pending_changed[key] = normalized
            cls._pending_ts[key] = now
        except Exception as exc:
            logger.warning("writeback schedule failed key=%s: %s", key, exc)

    @classmethod
    def schedule_user_movie_delete(cls, movie_id: int, tmdb_id, media_type) -> None:
        """UserMovie удалён → убрать из TMDB watchlist/favorite/rating."""
        from vault.tasks import tmdb_writeback_user_movie_delete

        cls._schedule(
            tmdb_writeback_user_movie_delete,
            f"um_delete:{movie_id}",
            (movie_id, tmdb_id, media_type),
        )

    @classmethod
    def schedule_list_item_added(cls, user_list_movie_id: int) -> None:
        """Фильм добавлен в UserList → list_add_items."""
        from vault.tasks import tmdb_writeback_list_item_added

        cls._schedule(
            tmdb_writeback_list_item_added,
            f"lm_add:{user_list_movie_id}",
            (user_list_movie_id,),
        )

    @classmethod
    def schedule_list_item_removed(cls, tmdb_list_id, tmdb_id, media_type) -> None:
        """Фильм удалён из UserList → list_remove_items."""
        from vault.tasks import tmdb_writeback_list_item_removed

        cls._schedule(
            tmdb_writeback_list_item_removed,
            f"lm_rm:{tmdb_list_id}:{tmdb_id}",
            (tmdb_list_id, tmdb_id, media_type),
        )

    @classmethod
    def schedule_list_sync(cls, user_list_id: int) -> None:
        """UserList создан/изменён → создать или обновить TMDB-лист."""
        from vault.tasks import tmdb_writeback_list_sync

        cls._schedule(tmdb_writeback_list_sync, f"list_sync:{user_list_id}", (user_list_id,))

    @classmethod
    def schedule_list_delete(cls, tmdb_list_id) -> None:
        """UserList удалён → delete_list."""
        from vault.tasks import tmdb_writeback_list_delete

        cls._schedule(
            tmdb_writeback_list_delete,
            f"list_del:{tmdb_list_id}",
            (tmdb_list_id,),
        )