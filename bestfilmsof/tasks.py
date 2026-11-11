"""Фоновые задачи bestfilmsof (Huey)."""

from __future__ import annotations

from django.db import close_old_connections

from movie_filter_pro.huey import HUEY


@HUEY.task()
def bestfilmsof_sync(year: int | None, genre: str, token: str):
    """Синк списка (year задан) или жанровой сводки (year=None)."""
    close_old_connections()
    from bestfilmsof.services.sync_service import SyncService

    return SyncService.run_claimed(year, genre, token)


@HUEY.task()
def bestfilmsof_backfill_metadata(year: int | None, genre: str):
    """Добор русских названий/синопсисов для уже сохранённого слепка."""
    close_old_connections()
    from bestfilmsof.services.metadata_service import backfill_pair

    return backfill_pair(year, genre)
