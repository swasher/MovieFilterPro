"""
Центральная точка формирования и выдачи изображений Vault.

Приложение (модели, API-сериализаторы) вызывает только :meth:`ImageService.url`
и ничего не знает про локальный кеш. Все URL указывают на внутренний endpoint
``/api/vault/images/...``; он отдаёт файл из дискового кеша, а пока файла нет —
временно перенаправляет браузер на TMDB и прогревает кеш в фоне.

Почему так:

* браузер никогда не ждёт, пока сервер скачает картинку: холодный кеш
  отдаётся редиректом на CDN, поэтому первая загрузка страницы быстрая;
* глобальный тумблер в Preferences полностью выключает дисковый кеш и
  возвращает прямые CDN-URL (для сравнения и отладки);
* URL изображения стабилен и не меняется при очистке кеша;
* кеш можно удалить целиком — приложение об этом не узнает;
* все правила (размеры, виды изображений, заглушки, безопасность пути)
  сосредоточены в одном месте.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlparse

from django.conf import settings
from django.http import HttpResponseRedirect, StreamingHttpResponse

from vault.services.image_cache import (
    CACHE_STATUS_MISSING,
    CACHE_STATUS_READY,
    CachedImage,
    ImageCache,
)

logger = logging.getLogger("vault.image_service")

# Размер чанка при отдаче файла. Держим его умеренным, чтобы не читать
# многомегабайтный original в память целиком.
FILE_STREAM_CHUNK_SIZE = 64 * 1024


class _AsyncFileIterator:
    """Читает файл чанками, не блокируя event loop.

    У объекта намеренно нет ``__iter__``: Django определяет async-ответ по
    неудачному ``iter(value)`` (``StreamingHttpResponse._set_streaming_content``).
    Если добавить sync-итератор, ASGI-путь снова начнёт материализовать весь
    файл через ``sync_to_async(list)(...)``.
    """

    def __init__(self, file_handle, chunk_size: int = FILE_STREAM_CHUNK_SIZE):
        self._file = file_handle
        self._chunk_size = chunk_size

    def _read(self) -> bytes:
        return self._file.read(self._chunk_size)

    def close(self) -> None:
        try:
            self._file.close()
        except OSError:
            pass

    async def __aiter__(self):
        try:
            while True:
                chunk = await asyncio.to_thread(self._read)
                if not chunk:
                    return
                yield chunk
        finally:
            self.close()

DEFAULT_IMAGE_KIND = "poster"
DEFAULT_IMAGE_SIZE = "w500"
API_PREFIX = "/api/vault/images"

# Размеры под конкретные места интерфейса. Каждый размер — отдельный файл
# дискового кеша, поэтому карточки в списках не должны тянуть те же файлы,
# что и крупные изображения на страницах-деталях: это лишние байты, лишняя
# загрузка и лишний файл на диске.
POSTER_CARD_SIZE = "w342"       # сетки фильмов, фильмография, сезоны, коллекции
POSTER_DETAIL_SIZE = "w500"     # постер на странице фильма
PROFILE_CARD_SIZE = "w185"      # карточки персон и состав на странице фильма
PROFILE_DETAIL_SIZE = "w500"    # главное фото на странице персоны
BACKDROP_CARD_SIZE = "w780"     # бэкдропы коллекций в карточках
BACKDROP_DETAIL_SIZE = "w1280"  # бэкдроп на странице фильма

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

# Настройка кеширования живёт в UserPreferences, но :meth:`ImageService.url`
# вызывается десятки раз на один ответ API. Держим значение в памяти с
# коротким TTL и сбрасываем его при сохранении Preferences.
_IMAGE_CACHE_ENABLED_TTL_SECONDS = 5.0
_image_cache_enabled_value = True
_image_cache_enabled_expires_at = 0.0
_image_cache_enabled_lock = threading.Lock()


class ImageService:
    """Единый контракт «путь TMDB -> URL изображения Vault»."""

    @classmethod
    def url(
        cls,
        raw_path: str | None,
        size: str = DEFAULT_IMAGE_SIZE,
        kind: str = DEFAULT_IMAGE_KIND,
    ) -> str | None:
        """Возвращает URL изображения или ``None``.

        По умолчанию — внутренний URL ``/api/vault/images/...`` (дисковый кеш
        Vault). Если глобальный тумблер в Preferences выключен — прямой URL CDN
        TMDB, чтобы работало только браузерное кеширование.

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

        if not cls._is_disk_cache_enabled():
            # Глобальный тумблер выключен: отдаём CDN-URL, чтобы работало
            # обычное браузерное кеширование (HTTP/2, параллельная загрузка).
            return cls.source_url(normalized_size, value)

        encoded_path = quote(value.lstrip("/"), safe="/")
        return f"{API_PREFIX}/{normalized_kind}/{normalized_size}/{encoded_path}"

    @classmethod
    def _is_disk_cache_enabled(cls) -> bool:
        global _image_cache_enabled_value, _image_cache_enabled_expires_at

        now = time.monotonic()
        if now < _image_cache_enabled_expires_at:
            return _image_cache_enabled_value

        try:
            from moviefilter.models import UserPreferences

            value = (
                UserPreferences.objects.filter(pk=1)
                .values_list("vault_image_cache_enabled", flat=True)
                .first()
            )
            enabled = True if value is None else bool(value)
        except Exception:  # noqa: BLE001 - пустая/недоступная БД не должна ломать картинки
            enabled = True

        with _image_cache_enabled_lock:
            _image_cache_enabled_value = enabled
            _image_cache_enabled_expires_at = (
                time.monotonic() + _IMAGE_CACHE_ENABLED_TTL_SECONDS
            )
        return enabled

    @classmethod
    def invalidate_cache_settings(cls) -> None:
        """Сбрасывает закешированное значение тумблера после сохранения Preferences."""
        global _image_cache_enabled_expires_at
        with _image_cache_enabled_lock:
            _image_cache_enabled_expires_at = 0.0

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
        """Отдаёт изображение из кеша, не дожидаясь скачивания.

        Горячий кеш — локальный файл с долгим браузерным кешем. Холодный —
        временный редирект на источник: браузер тянет картинку с CDN
        параллельно и быстро, а сервер в это время прогревает кеш в фоне.
        Заглушка нужна только когда источник подтвердил отсутствие файла.
        """
        if not cls.is_valid_request(kind, size, image_path):
            raise ValueError("Invalid image request")

        cache = cls._get_cache(kind, size)
        status, cached = cache.get_or_schedule(
            image_path, cls.source_url(size, image_path)
        )
        if status == CACHE_STATUS_READY and cached is not None:
            return cls._file_response(cached, kind)
        if status == CACHE_STATUS_MISSING:
            return cls._placeholder_response(kind)

        return cls._source_redirect_response(size, image_path)

    @classmethod
    def _file_response(cls, cached: CachedImage, kind: str) -> StreamingHttpResponse:
        try:
            file_handle = cached.path.open("rb")
        except OSError:
            logger.warning("Cached image disappeared before serving: %s", cached.path)
            return cls._placeholder_response(kind)

        try:
            file_stat = cached.path.stat()
        except OSError:
            logger.warning("Cached image disappeared before serving: %s", cached.path)
            file_handle.close()
            return cls._placeholder_response(kind)

        # Стримим файл чанками: ASGI больше не читает его целиком в память
        # перед отправкой (см. _AsyncFileIterator).
        response = StreamingHttpResponse(
            _AsyncFileIterator(file_handle),
            content_type=cached.content_type,
        )
        response["Content-Length"] = str(file_stat.st_size)
        # Путь TMDB иммутабелен: один и тот же URL всегда отдаёт один и тот же
        # файл. Поэтому браузер может держать его в кеше очень долго.
        # private, а не public: endpoint требует сессию, а общего
        # reverse-proxy кеша в деплое нет. Браузерный кеш private не ограничивает.
        response["Cache-Control"] = "private, max-age=31536000, immutable"
        response["ETag"] = f'"{file_stat.st_mtime_ns:x}-{file_stat.st_size:x}"'
        return response

    @classmethod
    def _source_redirect_response(cls, size: str, image_path: str):
        response = HttpResponseRedirect(cls.source_url(size, image_path))
        # Пока файл не скачан, тот же URL должен перенаправлять на источник.
        # Как только кеш прогреется, браузер получит уже локальную картинку,
        # поэтому сам редирект запоминать нельзя.
        response["Cache-Control"] = "no-store"
        return response

    @classmethod
    def _placeholder_response(cls, kind: str) -> StreamingHttpResponse | HttpResponseRedirect:
        """Отдаёт заглушку сразу, без редиректа на статику.

        Редирект добавлял лишний round-trip на каждую картинку, которой нет в
        источнике. Заглушка одинакова для всех запросов и не является секретом,
        поэтому отдаём её с ``200`` и коротким кешем: если источник позже
        начнёт отдавать файл (или маркер ``.missing`` истечёт), браузер
        подхватит его в пределах часа.
        """
        path = cls._placeholder_file(kind)
        if path is None:
            # Статика не найдена (например, не выполнен collectstatic):
            # не ломаем страницу, откатываемся на редирект.
            response = HttpResponseRedirect(cls.placeholder_url(kind))
            response["Cache-Control"] = "no-store"
            return response

        try:
            file_handle = path.open("rb")
            file_stat = path.stat()
        except OSError:
            logger.warning("Placeholder image disappeared before serving: %s", path)
            response = HttpResponseRedirect(cls.placeholder_url(kind))
            response["Cache-Control"] = "no-store"
            return response

        response = StreamingHttpResponse(
            _AsyncFileIterator(file_handle),
            content_type="image/svg+xml",
        )
        response["Content-Length"] = str(file_stat.st_size)
        response["Cache-Control"] = "private, max-age=3600"
        return response

    @staticmethod
    def _placeholder_file(kind: str) -> Path | None:
        # Импорт внутри функции: заглушка — редкий путь, а finders тянет
        # настройки статики, которые нужны не всем потребителям ImageService.
        from django.contrib.staticfiles import finders

        filename = PLACEHOLDER_FILENAMES.get(kind, PLACEHOLDER_FILENAMES[DEFAULT_IMAGE_KIND])
        try:
            found = finders.find(f"img/{filename}")
        except Exception:  # noqa: BLE001 - заглушка не должна ломать отдачу
            return None
        if not found:
            return None
        path = Path(found)
        return path if path.is_file() else None

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
