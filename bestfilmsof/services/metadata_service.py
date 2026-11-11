"""Добор русских метаданных для кеша bestfilmsof.

Английские метаданные приходят бесплатно внутри ответа bestfilmsof.
Русские названия/синопсисы берём из коллекции Vault (при чтении, без записи)
или добираем из TMDB фоновой задачей.
"""

from __future__ import annotations

import logging
import time

from tmdb_adapter.client_singleton import get_tmdb_client

from bestfilmsof.models import BestfilmsCache, BestfilmsEntry, BestfilmsGenreYear
from bestfilmsof.services.collection_service import get_collection_metadata

logger = logging.getLogger("bestfilmsof")


def _pair_tmdb_ids(year: int | None, genre: str) -> list[int]:
    if year is None:
        return list(
            BestfilmsGenreYear.objects.filter(genre=genre).values_list(
                "top_tmdb_id", flat=True
            )
        )
    return list(
        BestfilmsEntry.objects.filter(year=year, genre=genre).values_list(
            "tmdb_id", flat=True
        )
    )


def backfill_russian(tmdb_ids) -> dict:
    """Заполняет title_ru/overview_ru для кеш-строк, у которых их нет.

    Фильмы, которые уже есть в коллекции Vault, пропускаем: русские данные
    оттуда читаются при показе и не требуют запроса к TMDB.
    """
    ids = sorted({int(tmdb_id) for tmdb_id in tmdb_ids if tmdb_id})
    stats = {"requested": len(ids), "fetched": 0, "skipped_collection": 0, "errors": []}
    if not ids:
        return stats

    in_collection = get_collection_metadata(ids)
    missing = list(
        BestfilmsCache.objects.filter(tmdb_id__in=ids, title_ru__isnull=True)
        .exclude(tmdb_id__in=in_collection)
        .order_by("tmdb_id")
        .values_list("tmdb_id", flat=True)
    )
    stats["skipped_collection"] = len([tid for tid in ids if tid in in_collection])
    if not missing:
        return stats

    started = time.perf_counter()
    try:
        client = get_tmdb_client()
    except Exception as exc:  # нет ключа / битые настройки TMDB
        logger.warning("TMDB client is unavailable for bestfilmsof backfill: %s", exc)
        stats["errors"].append(str(exc))
        return stats

    rows = BestfilmsCache.objects.in_bulk(missing)
    for tmdb_id in missing:
        try:
            data = client._api.movies_get_details(tmdb_id, language="ru-RU")
        except Exception as exc:  # одна ошибка не должна ронять весь backfill
            logger.warning("TMDB RU details failed for %s: %s", tmdb_id, exc)
            stats["errors"].append(tmdb_id)
            continue

        row = rows.get(tmdb_id)
        if row is None or not isinstance(data, dict):
            stats["errors"].append(tmdb_id)
            continue

        row.title_ru = (data.get("title") or "").strip() or None
        row.overview_ru = (data.get("overview") or "").strip() or None
        stats["fetched"] += 1

    BestfilmsCache.objects.bulk_update(
        [row for row in rows.values() if row.title_ru],
        ["title_ru", "overview_ru"],
    )
    stats["seconds"] = round(time.perf_counter() - started, 2)
    logger.info(
        "bestfilmsof RU backfill: %s fetched, %s errors, %s skipped (collection)",
        stats["fetched"],
        len(stats["errors"]),
        stats["skipped_collection"],
    )
    return stats


def backfill_pair(year: int | None, genre: str) -> dict:
    """Фоновая задача после синка списка/сводки."""
    return backfill_russian(_pair_tmdb_ids(year, genre))
