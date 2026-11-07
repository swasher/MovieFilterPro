"""
Центральная точка формирования и выдачи изображений Vault.

Приложение (модели, API-сериализаторы) вызывает только :meth:`ImageService.url`
и ничего не знает про локальный кеш. Все URL указывают на внутренний endpoint
``/api/vault/images/...``; он отдаёт файл из дискового кеша и сам решает,
скачать ли изображение у TMDB.

Почему так:

* браузер никогда не зависит от внешнего CDN и его антибот-политик;
* URL изображения стабилен и не меняется при очистке кеша;
* кеш можно удалить целиком — приложение об этом не узнает;
* все правила (размеры, виды изображений, заглушки, безопасность пути)
  сосредоточены в одном месте.
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from urllib.parse import quote, urlparse

from django.conf import settings
from django.http import FileResponse, HttpResponseRedirect

from vault.services.image_cache import ImageCache

logger = logging.getLogger("vault.image_service")

DEFAULT_IMAGE_KIND = "poster"
DEFAULT_IMAGE_SIZE = "w500"
API_PREFIX = "/api/vault/images"

IMAGE_KINDS = frozenset({"poster", "backdrop", "profile"})

# Размеры, которые реально использует Vault и поддерживает TMDB.
# Не даём превратить endpoint в генератор произвольных upstream-запросов.
ALLOWED_IMAGE_SIZES = frozenset(
    {
        "w45",
        "w92",
        "w154",
        "w185",
        "w300",
        "w342",
        "w500",
        "w780",
        "w1280",
        "h632",
        "original",
    }
)

PLACEHOLDER_FILENAMES = {
    "poster": "poster-placeholder.svg",
    "backdrop": "backdrop-placeholder.svg",
    "profile": "profile-placeholder.svg",
}

_TMDB_SIZE_RE = re.compile(r"^(?:w|h)\d{2,4}$|^original$")
_SAFE_IMAGE_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_MAX_IMAGE_PATH_LENGTH = 512

_IMAGE_CACHES: dict[str, ImageCache] = {}
_IMAGE_CACHES_LOCK = threading.Lock()


class ImageService:
    """Единый контракт «путь TMDB -> URL изображения Vault»."""

    @classmethod
    def url(
        cls,
        raw_path: str | None,
        size: str = DEFAULT_IMAGE_SIZE,
        kind: str = DEFAULT_IMAGE_KIND,
    ) -> str | None:
        """Возвращает внутренний URL изображения или ``None``.

        ``raw_path`` — относительный путь TMDB (``/abc.jpg``), полный URL TMDB
        или уже готовый локальный URL. Чужие абсолютные URL не проксируются:
        они возвращаются как есть, чтобы не ломать пользовательские обложки.
        """
        value = cls._normalize_path(raw_path)
        if not value:
            return None

        parsed = urlparse(value)
        if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
            return value

        passthrough_prefixes = [
            f"{settings.STATIC_URL.rstrip('/')}/",
            f"{API_PREFIX}/",
        ]
        media_url = getattr(settings, "MEDIA_URL", "")
        if media_url:
            passthrough_prefixes.append(f"{media_url.rstrip('/')}/")
        if value.startswith(tuple(passthrough_prefixes)):
            return value

        normalized_kind = kind if kind in IMAGE_KINDS else DEFAULT_IMAGE_KIND
        normalized_size = size if size in ALLOWED_IMAGE_SIZES else DEFAULT_IMAGE_SIZE
        encoded_path = quote(value.lstrip("/"), safe="/")
        return f"{API_PREFIX}/{normalized_kind}/{normalized_size}/{encoded_path}"

    @classmethod
    def source_url(cls, size: str, image_path: str) -> str:
        """Собирает URL источника. Вызывать только после валидации пути."""
        base_url = getattr(settings, "TMDB_IMAGE_BASE_URL", "https://image.tmdb.org/t/p/")
        base_url = base_url.rstrip("/") + "/"
        return f"{base_url}{size}/{image_path.lstrip('/')}"

    @classmethod
    def placeholder_url(cls, kind: str) -> str:
        filename = PLACEHOLDER_FILENAMES.get(kind, PLACEHOLDER_FILENAMES[DEFAULT_IMAGE_KIND])
        return f"{settings.STATIC_URL.rstrip('/')}/img/{filename}"

    @classmethod
    def is_valid_request(cls, kind: str, size: str, image_path: str) -> bool:
        if kind not in IMAGE_KINDS or size not in ALLOWED_IMAGE_SIZES:
            return False
        if not image_path or len(image_path) > _MAX_IMAGE_PATH_LENGTH:
            return False
        if not _SAFE_IMAGE_PATH_RE.fullmatch(image_path):
            return False
        if any(segment in {"", ".", ".."} for segment in image_path.split("/")):
            return False
        return True

    @classmethod
    def serve(cls, kind: str, size: str, image_path: str):
        """Отдаёт изображение из кеша; при неудаче — заглушку."""
        if not cls.is_valid_request(kind, size, image_path):
            raise ValueError("Invalid image request")

        cache = cls._get_cache(kind, size)
        cached = cache.get(image_path, cls.source_url(size, image_path))
        if cached is None:
            return cls._placeholder_response(kind)

        try:
            file_handle = cached.path.open("rb")
        except OSError:
            logger.warning("Cached image disappeared before serving: %s", cached.path)
            return cls._placeholder_response(kind)

        response = FileResponse(file_handle, content_type=cached.content_type)
        # Путь TMDB иммутабелен: один и тот же URL всегда отдаёт один и тот же
        # файл. Поэтому браузер может держать его в кеше очень долго.
        response["Cache-Control"] = "private, max-age=31536000, immutable"
        try:
            stat = cached.path.stat()
        except OSError:
            pass
        else:
            response["ETag"] = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        return response

    @classmethod
    def _placeholder_response(cls, kind: str):
        response = HttpResponseRedirect(cls.placeholder_url(kind))
        # Промежуточное состояние нельзя запоминать: после появления файла
        # браузер должен получить уже настоящую картинку.
        response["Cache-Control"] = "no-store"
        return response

    @classmethod
    def _get_cache(cls, kind: str, size: str) -> ImageCache:
        # Каталог зависит от настроек, поэтому экземпляры кеша индексируются
        # по фактическому пути: override_settings(CACHE_ROOT=...) в тестах
        # автоматически получает отдельный кеш.
        root = Path(settings.CACHE_ROOT) / "vault" / kind / size
        root_key = str(root)
        with _IMAGE_CACHES_LOCK:
            cache = _IMAGE_CACHES.get(root_key)
            if cache is None:
                cache = ImageCache(root)
                _IMAGE_CACHES[root_key] = cache
            return cache

    @classmethod
    def _normalize_path(cls, raw_path: str | None) -> str | None:
        if raw_path is None:
            return None

        value = str(raw_path).strip()
        if not value:
            return None

        parsed = urlparse(value)
        if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
            base_host = urlparse(cls._tmdb_base_url()).hostname or ""
            if (parsed.hostname or "").lower() != base_host.lower():
                return value
            value = parsed.path

        value = value.split("?", 1)[0].split("#", 1)[0]
        value = cls._strip_tmdb_prefix(value)
        if not value or value == "/":
            return None
        return "/" + value.lstrip("/")

    @classmethod
    def _strip_tmdb_prefix(cls, value: str) -> str:
        base_path = urlparse(cls._tmdb_base_url()).path
        if not base_path.endswith("/"):
            base_path += "/"

        for prefix in (base_path, base_path.lstrip("/")):
            if prefix and value.startswith(prefix):
                value = value[len(prefix):]
                break

        head, separator, tail = value.partition("/")
        if separator and _TMDB_SIZE_RE.fullmatch(head):
            return tail
        return value

    @staticmethod
    def _tmdb_base_url() -> str:
        return getattr(settings, "TMDB_IMAGE_BASE_URL", "https://image.tmdb.org/t/p/")
