from __future__ import annotations

import logging
from datetime import date

from tmdb_adapter.client_singleton import get_tmdb_client
from vault.models import Collection, Movie

logger = logging.getLogger("vault.collection_sync")

# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #


class CollectionService:
    """Синхронизация TMDB коллекций (belongs_to_collection) -> локальный снапшот."""

    @classmethod
    def sync_collection_for_movie(cls, movie: Movie, tmdb_collection_obj) -> Collection | None:
        """
        Создаёт/обновляет Collection по tmdb_collection_obj и привязывает к movie.
        Если tmdb_collection_obj is None — отвязывает movie.collection = None.
        Возвращает Collection или None. Не кидает наружу (логирует).
        Collection в TMDB существует только для movie — для tv сюда не идём (проверка выше).
        """
        # Отвязка
        if tmdb_collection_obj is None:
            if movie.collection_id is not None:
                movie.collection = None
                try:
                    movie.save(update_fields=["collection"])
                except Exception:
                    logger.warning("Failed to detach collection from movie_id=%s", movie.id, exc_info=True)
            return None

        # Извлекаем поля из объекта Collection (tmdbapis) или dict
        tmdb_id = cls._extract_tmdb_id(tmdb_collection_obj)
        if not tmdb_id:
            logger.warning("sync_collection_for_movie: no tmdb_id in %r", tmdb_collection_obj)
            return None

        name = cls._extract_str(tmdb_collection_obj, "name") or f"Collection {tmdb_id}"
        overview = cls._extract_str(tmdb_collection_obj, "overview") or ""
        poster_path = cls._extract_str_or_none(tmdb_collection_obj, "poster_path")
        backdrop_path = cls._extract_str_or_none(tmdb_collection_obj, "backdrop_path")

        # get_or_create
        collection, created = Collection.objects.get_or_create(
            tmdb_id=tmdb_id,
            defaults={
                "name": name[:500],
                "overview": overview,
                "poster_path": poster_path,
                "backdrop_path": backdrop_path,
            },
        )
        # Обновить мета если изменились
        updated_fields: list[str] = []
        if collection.name != name[:500]:
            collection.name = name[:500]
            updated_fields.append("name")
        if collection.overview != overview:
            collection.overview = overview
            updated_fields.append("overview")
        if collection.poster_path != poster_path:
            collection.poster_path = poster_path
            updated_fields.append("poster_path")
        if collection.backdrop_path != backdrop_path:
            collection.backdrop_path = backdrop_path
            updated_fields.append("backdrop_path")
        if updated_fields:
            try:
                collection.save(update_fields=updated_fields)
            except Exception:
                logger.warning("Failed to update Collection tmdb_id=%s", tmdb_id, exc_info=True)

        # Синк parts_data отдельным запросом (не ломает первый save)
        try:
            cls._sync_parts_data(collection)
        except Exception:
            logger.warning("Failed to sync parts for collection tmdb_id=%s", tmdb_id, exc_info=True)

        # Привязать к фильму
        if movie.collection_id != collection.id:
            movie.collection = collection
            try:
                movie.save(update_fields=["collection"])
            except Exception:
                logger.warning("Failed to attach collection to movie_id=%s", movie.id, exc_info=True)

        return collection

    @classmethod
    def _sync_parts_data(cls, collection: Collection) -> bool:
        """
        Делает дополнительный запрос TMDB для коллекции и собирает parts_data.
        Возвращает True если данные изменились.
        """
        try:
            tmdb = get_tmdb_client()
        except Exception:
            logger.debug("get_tmdb_client failed for collection sync", exc_info=True)
            return False

        try:
            # Collection() в tmdbapis грузит parts через _full_load -> collections_get_details
            details = tmdb.collection(collection.tmdb_id)
        except Exception:
            logger.warning("tmdb.collection(%s) failed", collection.tmdb_id, exc_info=True)
            return False

        # parts хранятся как details.movies (alias parts)
        raw_parts = getattr(details, "movies", None)
        if raw_parts is None:
            raw_parts = getattr(details, "parts", None)
        if raw_parts is None:
            raw_parts = []

        new_parts: list[dict] = []
        for idx, part in enumerate(list(raw_parts or [])):
            try:
                part_tmdb_id = getattr(part, "id", None)
                if part_tmdb_id is None:
                    part_tmdb_id = getattr(part, "tmdb_id", None)
                if part_tmdb_id is None and isinstance(part, dict):
                    part_tmdb_id = part.get("id") or part.get("tmdb_id")
                if not part_tmdb_id:
                    continue
                part_tmdb_id = int(part_tmdb_id)

                title = cls._extract_str(part, "title") or cls._extract_str(part, "name") or ""
                original_title = cls._extract_str(part, "original_title") or cls._extract_str(part, "original_name") or ""
                poster_path = cls._extract_str_or_none(part, "poster_path")
                release_date = getattr(part, "release_date", None)
                if release_date is None and isinstance(part, dict):
                    release_date = part.get("release_date")
                # release_date может быть datetime/date/str
                year: int | None = None
                release_date_str: str | None = None
                if release_date is not None:
                    if hasattr(release_date, "year"):
                        try:
                            year = int(release_date.year)
                            # сериализуем как ISO date для хранения
                            if hasattr(release_date, "isoformat"):
                                release_date_str = release_date.isoformat()[:10]
                            else:
                                release_date_str = str(release_date)[:10]
                        except Exception:
                            pass
                    elif isinstance(release_date, str):
                        release_date_str = release_date.strip() or None
                        if release_date_str and len(release_date_str) >= 4:
                            try:
                                year = int(release_date_str[:4])
                            except Exception:
                                year = None
                    else:
                        release_date_str = str(release_date)[:10]

                # Fallback year from part.year if present
                if year is None:
                    raw_year = getattr(part, "year", None)
                    if raw_year is not None:
                        try:
                            year = int(raw_year)
                        except Exception:
                            pass

                new_parts.append(
                    {
                        "tmdb_id": part_tmdb_id,
                        "title": title[:500],
                        "original_title": original_title[:500],
                        "poster_path": poster_path,
                        "release_date": release_date_str,
                        "year": year,
                        "order": idx,
                    }
                )
            except Exception:
                logger.debug("Failed to parse collection part idx=%s", idx, exc_info=True)
                continue

        # Сравниваем с текущим (порядок важен)
        current = collection.parts_data or []
        # Простая проверка: сериализованное сравнение (без учёта ключей порядка)
        if current == new_parts:
            return False

        # Если отличается — атомарно обновляем
        collection.parts_data = new_parts
        try:
            collection.save(update_fields=["parts_data", "updated_at"])
        except Exception:
            logger.warning("Failed to save parts_data for collection %s", collection.tmdb_id, exc_info=True)
            return False
        return True

    # --- helpers ---

    @staticmethod
    def _extract_tmdb_id(obj) -> int | None:
        for attr in ("id", "tmdb_id"):
            val = getattr(obj, attr, None)
            if val is not None:
                try:
                    return int(val)
                except Exception:
                    pass
            if isinstance(obj, dict) and attr in obj:
                try:
                    return int(obj[attr])
                except Exception:
                    pass
        return None

    @staticmethod
    def _extract_str(obj, name: str) -> str:
        val = getattr(obj, name, None)
        if val is not None:
            return str(val).strip()
        if isinstance(obj, dict) and name in obj:
            return str(obj[name] or "").strip()
        # пробуем dict с ключом id/title в случае обёртки
        return ""

    @staticmethod
    def _extract_str_or_none(obj, name: str) -> str | None:
        val = getattr(obj, name, None)
        if val is not None:
            s = str(val).strip()
            return s or None
        if isinstance(obj, dict) and name in obj:
            s = str(obj[name] or "").strip()
            return s or None
        return None


# ------------------------------------ #
#            DOMAIN LAYER              #
# ------------------------------------ #

# Чистая функция для возможного reuse

def build_collection_parts_snapshot(tmdb_parts: list) -> list[dict]:
    """Утилита для тестов: собрать parts_data из сырых parts."""
    snapshot = []
    for idx, part in enumerate(tmdb_parts or []):
        snapshot.append(
            {
                "tmdb_id": getattr(part, "id", part.get("id") if isinstance(part, dict) else None),
                "title": getattr(part, "title", ""),
                "original_title": getattr(part, "original_title", ""),
                "poster_path": getattr(part, "poster_path", None),
                "release_date": str(getattr(part, "release_date", "")),
                "year": None,
                "order": idx,
            }
        )
    return snapshot
