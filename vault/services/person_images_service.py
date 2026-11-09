"""Список фотографий персоны из TMDB.

Список profile-файлов у персоны практически не меняется, поэтому он
кешируется без TTL: страница персоны больше не ходит в TMDB на каждый
просмотр. Кеш живёт в процессе (LocMem), после рестарта список один раз
перечитается из TMDB.
"""

from __future__ import annotations

import logging

from django.core.cache import cache

from tmdb_adapter.client_singleton import get_person_images, get_tmdb_client

logger = logging.getLogger("vault.person_images")

# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #

CACHE_KEY_PREFIX = "vault:person-images:"

# get_person_images всё равно зажимает лимит до 20.
MAX_CACHED_IMAGES = 20


def get_person_image_paths(tmdb_person_id: int) -> list[str]:
    """Возвращает пути profile-файлов персоны (кешируется без истечения).

    ``TmdbRateLimiter`` здесь намеренно не используется: вызов одиночный,
    интерактивный и выполняется один раз на персону за жизнь процесса —
    это не пакетная операция, ради которой лимитер и существует. Пакетный
    sync работает в отдельном HUEY-процессе со своим лимитером.
    """
    cache_key = f"{CACHE_KEY_PREFIX}{tmdb_person_id}"

    cached = cache.get(cache_key)
    if cached is not None:
        return list(cached)

    images = get_person_images(
        get_tmdb_client(),
        tmdb_person_id,
        limit=MAX_CACHED_IMAGES,
    )
    paths = [image.file_path for image in images]

    # Пустой список тоже кешируем: значит у персоны просто нет фото в TMDB.
    cache.set(cache_key, paths, timeout=None)
    return paths
