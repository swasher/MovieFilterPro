"""Синхронизация слепков bestfilmsof: claim -> фоновая задача -> статус."""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from bestfilmsof.client import BestfilmsofClient
from bestfilmsof.constants import PAGE_LIMIT
from bestfilmsof.models import (
    BestfilmsCache,
    BestfilmsEntry,
    BestfilmsGenreYear,
    BestfilmsSync,
)
from bestfilmsof.parsing import ENTRY_FIELDS, metadata_from_raw, parse_entry
from bestfilmsof.services.read_service import norm_genre

logger = logging.getLogger("bestfilmsof")

# Задача потерялась/воркер не запущен: через сколько секунд claim её перезапустит.
QUEUE_PICKUP_TIMEOUT = timedelta(seconds=60)
# Если задача уже реально выполняется — не трогаем её дольше этого времени.
RUNNING_TIMEOUT = timedelta(minutes=30)
# После ошибки не долбим упавший источник на каждом открытии страницы.
ERROR_RETRY_COOLDOWN = timedelta(minutes=1)
# Защита от бесконечного обхода при неадекватном totalPages.
MAX_PAGES = 100
# Сколько страниц списка тянем параллельно (каждая — в своём HTTP-клиенте).
PAGE_FETCH_WORKERS = 4


def _fetch_pages(year: int, genre: str, pages: list[int]) -> list[tuple[int, dict]]:
    """Параллельно скачивает страницы списка, сохраняя порядок."""

    def fetch(page: int) -> tuple[int, dict]:
        with BestfilmsofClient() as client:
            return page, client.fetch_page(year, genre, page=page, limit=PAGE_LIMIT)

    workers = min(PAGE_FETCH_WORKERS, len(pages))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fetch, pages))


def _parse_entries(movies: list[dict]) -> tuple[dict[str, dict], dict[int, dict]]:
    """Сырые фильмы bestfilmsof -> строки БД + метаданные TMDB для кеша."""
    fresh: dict[str, dict] = {}
    metadata: dict[int, dict] = {}
    for position, raw in enumerate(movies, start=1):
        data = parse_entry(raw, position)
        if data is None:
            continue
        fresh[raw["imdb_id"]] = data
        meta = metadata_from_raw(raw)
        if meta is not None:
            metadata[meta["tmdb_id"]] = meta
    return fresh, metadata


def sync_key(year: int | None, genre: str | None) -> str:
    norm = norm_genre(genre)
    if year is None:
        return f"summary:{norm}"
    return f"list:{year}:{norm}"


def _stale_ttl(year: int | None, now) -> timedelta:
    """Политика свежести из прототипа.

    Текущий год — 24 часа; прошлый — 7 дней (30 после 1 апреля, когда сезон
    наград закончился); архив — 90 дней. Сводки (year=None) живые — 24 часа.
    """
    if year is None or year >= now.year:
        return timedelta(days=1)
    if year == now.year - 1:
        if now < now.replace(month=4, day=1):
            return timedelta(days=7)
        return timedelta(days=30)
    return timedelta(days=90)


def is_stale(year: int | None, genre: str | None, synced_at, now=None) -> bool:
    now = now or timezone.now()
    if synced_at is None:
        return True
    return now - synced_at >= _stale_ttl(year, now)


class SyncService:
    """Единая точка запуска синка и ведения строки BestfilmsSync."""

    @staticmethod
    def _row(year: int | None, genre: str | None) -> BestfilmsSync | None:
        return BestfilmsSync.objects.filter(key=sync_key(year, genre)).first()

    @classmethod
    def claim(cls, year: int | None, genre: str | None, *, force: bool = False):
        """Атомарно занимает синк.

        Возвращает (claimed, row, token). Если синк уже идёт или данные свежие
        (и force=False) — claimed=False, row — текущее состояние.
        """
        norm = norm_genre(genre)
        key = sync_key(year, norm)
        now = timezone.now()

        with transaction.atomic():
            row, _ = BestfilmsSync.objects.get_or_create(
                key=key,
                defaults={"year": year, "genre": norm},
            )
            row = BestfilmsSync.objects.select_for_update().get(pk=row.pk)

            if row.status == BestfilmsSync.Status.RUNNING:
                worker_running = (
                    row.worker_started_at is not None
                    and now - row.worker_started_at < RUNNING_TIMEOUT
                )
                if worker_running:
                    return False, row, ""
                # Задача ещё не подхвачена воркером. Даём ему короткое время,
                # затем считаем задачу потерянной (воркер не запущен/перезапущен
                # без нового кода) и ставим заново. Старый токен обесценится.
                queued_recently = (
                    row.worker_started_at is None
                    and row.started_at is not None
                    and now - row.started_at < QUEUE_PICKUP_TIMEOUT
                    and not force
                )
                if queued_recently:
                    return False, row, ""

            error_recently = (
                not force
                and row.status == BestfilmsSync.Status.ERROR
                and row.finished_at is not None
                and now - row.finished_at < ERROR_RETRY_COOLDOWN
            )
            if error_recently:
                return False, row, ""
            if not force and row.synced_at and not is_stale(year, norm, row.synced_at, now):
                return False, row, ""

            row.year = year
            row.genre = norm
            row.status = BestfilmsSync.Status.RUNNING
            row.run_token = uuid.uuid4().hex
            row.started_at = now
            row.worker_started_at = None
            row.finished_at = None
            row.error_message = ""
            row.save(
                update_fields=[
                    "year",
                    "genre",
                    "status",
                    "run_token",
                    "started_at",
                    "worker_started_at",
                    "finished_at",
                    "error_message",
                ]
            )
            return True, row, row.run_token

    @classmethod
    def run_claimed(cls, year: int | None, genre: str | None, token: str) -> dict:
        """Выполняет синк, если claim всё ещё наш (защита от повторных задач)."""
        norm = norm_genre(genre)
        key = sync_key(year, norm)
        row = BestfilmsSync.objects.filter(key=key).first()
        if (
            row is None
            or row.status != BestfilmsSync.Status.RUNNING
            or row.run_token != token
        ):
            logger.info("bestfilmsof sync skipped (stale claim): %s", key)
            return {"status": "skipped", "key": key}

        # Атомарно фиксируем, что воркер действительно начал работу. Если за это
        # время claim перезапустили (другой токен) — старая задача уступает.
        if not BestfilmsSync.objects.filter(
            key=key,
            run_token=token,
            status=BestfilmsSync.Status.RUNNING,
        ).update(worker_started_at=timezone.now()):
            logger.info("bestfilmsof sync skipped (claim replaced): %s", key)
            return {"status": "skipped", "key": key}

        started = time.perf_counter()
        try:
            if year is None:
                stats = cls._sync_genre(norm)
            else:
                stats = cls._sync_list(year, norm)
        except Exception as exc:
            logger.exception("bestfilmsof sync failed: %s", key)
            BestfilmsSync.objects.filter(key=key, run_token=token).update(
                status=BestfilmsSync.Status.ERROR,
                finished_at=timezone.now(),
                error_message=str(exc)[:2000],
            )
            return {"status": "error", "key": key, "error": str(exc)}

        stats["seconds"] = round(time.perf_counter() - started, 2)
        BestfilmsSync.objects.filter(key=key, run_token=token).update(
            status=BestfilmsSync.Status.IDLE,
            synced_at=timezone.now(),
            finished_at=timezone.now(),
            error_message="",
            last_stats=stats,
        )
        logger.info(
            "bestfilmsof sync done: %s (%ss)",
            key,
            stats["seconds"],
        )
        return {"status": "ok", "key": key, "stats": stats}

    @classmethod
    def _store_entries(
        cls,
        year: int,
        genre: str,
        fresh: dict[str, dict],
        *,
        delete_stale: bool,
    ) -> dict:
        """Upsert строк списка. delete_stale=False — частичная запись первой страницы."""
        stats = {"created": 0, "updated": 0, "deleted": 0}
        with transaction.atomic():
            stored = {
                entry.imdb_id: entry
                for entry in BestfilmsEntry.objects.filter(year=year, genre=genre)
            }
            to_create = []
            to_update = []
            for imdb_id, data in fresh.items():
                obj = stored.get(imdb_id)
                if obj is None:
                    to_create.append(
                        BestfilmsEntry(year=year, genre=genre, imdb_id=imdb_id, **data)
                    )
                elif any(getattr(obj, field) != data[field] for field in ENTRY_FIELDS):
                    for field in ENTRY_FIELDS:
                        setattr(obj, field, data[field])
                    to_update.append(obj)
            stale_ids = (
                [entry.pk for imdb_id, entry in stored.items() if imdb_id not in fresh]
                if delete_stale
                else []
            )
            if to_create:
                BestfilmsEntry.objects.bulk_create(to_create)
            if to_update:
                BestfilmsEntry.objects.bulk_update(to_update, ENTRY_FIELDS)
            if stale_ids:
                BestfilmsEntry.objects.filter(pk__in=stale_ids).delete()

            stats.update(
                created=len(to_create),
                updated=len(to_update),
                deleted=len(stale_ids),
            )
        return stats

    @classmethod
    def _sync_list(cls, year: int, genre: str) -> dict:
        stats = {
            "mode": "list",
            "year": year,
            "genre": genre,
            "entries_total": 0,
            "entries_created": 0,
            "entries_updated": 0,
            "entries_deleted": 0,
            "cache_created": 0,
            "bestfilm_requests": 0,
        }

        t0 = time.perf_counter()
        with BestfilmsofClient() as client:
            first = client.fetch_page(year, genre, page=1, limit=PAGE_LIMIT)
            pagination = first.get("pagination") or {}
            total_pages = max(1, int(pagination.get("totalPages") or 1))
            total_pages = min(total_pages, MAX_PAGES)
            movies = list(first.get("movies") or [])

        # Первую страницу сохраняем сразу: фронт покажет фильмы, пока
        # догружаются остальные страницы (порядок до конца синка не финальный).
        partial_fresh, partial_metadata = _parse_entries(movies)
        partial_stats = cls._store_entries(year, genre, partial_fresh, delete_stale=False)
        stats["cache_created"] += _create_missing_cache(partial_metadata)

        extra_pages = list(range(2, total_pages + 1))
        if extra_pages:
            for _page, payload in _fetch_pages(year, genre, extra_pages):
                movies.extend(payload.get("movies") or [])

        stats["bestfilm_requests"] = total_pages
        stats["timings"] = {"bestfilm_s": round(time.perf_counter() - t0, 2)}

        fresh, metadata = _parse_entries(movies)
        stats["entries_total"] = len(fresh)

        t0 = time.perf_counter()
        store_stats = cls._store_entries(year, genre, fresh, delete_stale=True)
        # Учитываем и частичную запись, и финальную сверку.
        stats["entries_created"] = partial_stats["created"] + store_stats["created"]
        stats["entries_updated"] = partial_stats["updated"] + store_stats["updated"]
        stats["entries_deleted"] = store_stats["deleted"]
        stats["timings"]["entries_s"] = round(time.perf_counter() - t0, 2)

        stats["cache_created"] += _create_missing_cache(metadata)
        _enqueue_russian_backfill(year, genre)
        return stats

    @classmethod
    def _sync_genre(cls, genre: str) -> dict:
        stats = {
            "mode": "summary",
            "year": None,
            "genre": genre,
            "years_total": 0,
            "years_created": 0,
            "years_updated": 0,
            "cache_created": 0,
            "bestfilm_requests": 1,
        }

        t0 = time.perf_counter()
        with BestfilmsofClient() as client:
            payload = client.fetch_genre_summary(genre)
        stats["timings"] = {"bestfilm_s": round(time.perf_counter() - t0, 2)}

        rows = payload.get("years") or []
        metadata: dict[int, dict] = {}
        stats["years_total"] = len(rows)

        with transaction.atomic():
            stored = {
                row.year: row
                for row in BestfilmsGenreYear.objects.filter(genre=genre)
            }
            to_create = []
            to_update = []
            for item in rows:
                movie = item.get("movie") or {}
                meta = movie.get("metadata") or {}
                tmdb_id = _to_int(meta.get("id"))
                if not item.get("year") or not movie.get("imdb_id") or not tmdb_id:
                    continue
                values = {
                    "count": item.get("count") or 0,
                    "top_imdb_id": movie["imdb_id"],
                    "top_tmdb_id": tmdb_id,
                    "top_title": movie.get("primary_title")
                    or meta.get("title")
                    or movie["imdb_id"],
                    "top_score": movie.get("weighted_score"),
                }
                parsed_meta = metadata_from_raw(movie)
                if parsed_meta is not None:
                    metadata[tmdb_id] = parsed_meta

                row = stored.get(item["year"])
                if row is None:
                    to_create.append(
                        BestfilmsGenreYear(year=item["year"], genre=genre, **values)
                    )
                elif any(getattr(row, field) != value for field, value in values.items()):
                    for field, value in values.items():
                        setattr(row, field, value)
                    to_update.append(row)
            if to_create:
                BestfilmsGenreYear.objects.bulk_create(to_create)
            if to_update:
                BestfilmsGenreYear.objects.bulk_update(
                    to_update,
                    ["count", "top_imdb_id", "top_tmdb_id", "top_title", "top_score"],
                )
            stats["years_created"] = len(to_create)
            stats["years_updated"] = len(to_update)

        stats["cache_created"] = _create_missing_cache(metadata)
        _enqueue_russian_backfill(None, genre)
        return stats


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _create_missing_cache(metadata: dict[int, dict]) -> int:
    """Создаёт недостающие строки кеша из бесплатных метаданных bestfilmsof."""
    if not metadata:
        return 0
    existing = set(
        BestfilmsCache.objects.filter(tmdb_id__in=metadata).values_list(
            "tmdb_id", flat=True
        )
    )
    objects = [
        BestfilmsCache(**values)
        for tmdb_id, values in metadata.items()
        if tmdb_id not in existing
    ]
    if not objects:
        return 0
    BestfilmsCache.objects.bulk_create(objects, ignore_conflicts=True)
    return len(objects)


def _enqueue_russian_backfill(year: int | None, genre: str) -> None:
    """Русские метаданные догружаем отдельной задачей, не задерживая список."""
    try:
        from bestfilmsof.tasks import bestfilmsof_backfill_metadata

        bestfilmsof_backfill_metadata(year, genre)
    except Exception:
        # Неудачная постановка в очередь не должна ломать сам синк.
        logger.exception("failed to enqueue bestfilmsof RU backfill: %s/%s", year, genre)
