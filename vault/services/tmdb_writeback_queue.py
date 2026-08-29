"""
Очередь фоновых write-back задач (Фаза 1 — заглушка, Фаза 2 — async retry).

Пока сигналы вызывают write-back синхронно через transaction.on_commit.
Этот модуль готовит HUEY-задачи для будущего перехода на асинхронный режим
с delay + дедупликацией (см. PLAN §5, §12.3).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("vault.tmdb_writeback")


def schedule_writeback(user_movie_id: int, delay: int = 0):
    """
    Поставить write-back в очередь. Сейчас — синхронный фолбэк,
    позже — HUEY schedule с дедупликацией.
    """
    try:
        # пробуем HUEY если воркер запущен, иначе синхронно
        from vault.tasks import tmdb_writeback_user_movie as huey_task

        if delay:
            huey_task.schedule(args=(user_movie_id,), delay=delay)
            logger.debug("writeback queued via HUEY user_movie=%s delay=%s", user_movie_id, delay)
        else:
            # для единичных операций — пробуем HUEY без задержки, фолбэк синхронно
            try:
                huey_task(user_movie_id)
            except Exception:
                # если HUEY не запущен — синхронно
                from vault.services.tmdb_writeback_service import TmdbWritebackService

                TmdbWritebackService.sync_user_movie_to_tmdb_by_id(user_movie_id)
        return True
    except Exception as exc:
        logger.warning("writeback queue fallback sync user_movie=%s: %s", user_movie_id, exc)
        try:
            from vault.services.tmdb_writeback_service import TmdbWritebackService

            TmdbWritebackService.sync_user_movie_to_tmdb_by_id(user_movie_id)
        except Exception as inner:
            logger.exception("writeback sync fallback failed: %s", inner)
        return False
