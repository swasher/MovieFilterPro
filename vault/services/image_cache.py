"""
Дисковый кеш изображений Vault.

Модуль намеренно не знает ни про TMDB, ни про модели Vault: на вход он
получает произвольный ключ и URL источника, на выход отдаёт локальный файл.
Это позволяет использовать его для постеров, бэкдропов и фотографий персон
без привязки к конкретной сущности.

Механика повторяет проверенный кеш постеров Kinozal
(``moviefilter/image_caching.py``): атомарная запись через временный файл,
маркеры ``.missing`` / ``.failed`` и single-flight-загрузка в пределах процесса.
Но переиспользовать сам модуль Kinozal нельзя: он жёстко связан с
``MovieRSS`` (``movie_pk``), приоритетами и антибот-логикой fastpic.

Два режима доступа:

* :meth:`ImageCache.get` — блокирующий (скачивает файл прямо в вызывающем
  потоке); удобен для тестов и фоновых задач.
* :meth:`ImageCache.get_or_schedule` — неблокирующий: возвращает текущее
  состояние и при промахе ставит загрузку в общий пул. Именно им пользуется
  HTTP-endpoint, чтобы не заставлять браузер ждать, пока сервер скачает
  картинку у TMDB.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

logger = logging.getLogger("vault.image_cache")

MISSING_MARKER_SUFFIX = ".missing"
FAILED_MARKER_SUFFIX = ".failed"

# Версия маркера отсутствия. Позволяет инвалидировать маркеры, созданные
# старой/ошибочной версией загрузчика.
MISSING_MARKER_VERSION = "1"

DEFAULT_MISSING_TTL_SECONDS = 24 * 60 * 60
DEFAULT_FAILED_TTL_SECONDS = 30

# Загрузки идут в фоне, поэтому таймауты короткие: «плохая» картинка не должна
# держать воркер пула десятки секунд и тормозить прогрев остальных.
DEFAULT_REQUEST_TIMEOUT = (3, 8)

# Состояния кеша для неблокирующего режима.
CACHE_STATUS_READY = "ready"
CACHE_STATUS_PENDING = "pending"
CACHE_STATUS_MISSING = "missing"

# Сколько картинок прогреваем одновременно. Браузер всё равно откроет
# не больше шести соединений к нашему origin, а загрузки идут в фоне.
DEFAULT_DOWNLOAD_WORKERS = 8

# Дедупликация загрузок: фиксированный набор локов-«полос». Словарь локов на
# каждый ключ рос бы вместе с числом увиденных картинок и жил бы до рестарта.
LOCK_STRIPES = 128

# Защита от случайного/вредоносного ответа гигантского размера.
MAX_IMAGE_BYTES = 32 * 1024 * 1024

# Некоторые CDN отвечают 403 на User-Agent python-requests, поэтому
# представляемся обычным браузером.
IMAGE_REQUEST_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/156.0.0.0 Safari/537.36"
)

_SAFE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}

_download_executor: ThreadPoolExecutor | None = None
_download_executor_guard = threading.Lock()

# Одна requests.Session на поток процесса, а не на каждый ImageCache.
# Воркеры пула живут долго, поэтому TCP/TLS-соединения к TMDB
# переиспользуются между разными kind/size, а не только внутри одной пары.
_session_local = threading.local()


def _get_download_executor() -> ThreadPoolExecutor:
    """Общий на процесс пул фоновых загрузок.

    Потоки пула живут долго, поэтому thread-local ``requests.Session``
    внутри них переиспользует TCP/TLS-соединения к TMDB между картинками.
    """
    global _download_executor
    with _download_executor_guard:
        if _download_executor is None:
            _download_executor = ThreadPoolExecutor(
                max_workers=DEFAULT_DOWNLOAD_WORKERS,
                thread_name_prefix="vault-image",
            )
        return _download_executor


class ImageCacheError(Exception):
    """Базовая ошибка загрузки изображения."""


class ImageNotFoundError(ImageCacheError):
    """Источник подтвердил, что изображения нет (404/410)."""


class ImageContentTypeError(ImageCacheError):
    """Источник вернул не изображение."""


class ImageTooLargeError(ImageCacheError):
    """Ответ источника превысил допустимый размер."""


@dataclass(frozen=True)
class CachedImage:
    path: Path
    content_type: str


class ImageCache:
    """Кеш изображений в одном каталоге.

    ``key`` — стабильный идентификатор изображения (например, ``/poster.jpg``).
    ``source_url`` — откуда файл можно скачать. Один и тот же ключ всегда
    соответствует одному и тому же источнику.
    """

    def __init__(
        self,
        root: Path,
        *,
        missing_ttl_seconds: int = DEFAULT_MISSING_TTL_SECONDS,
        failed_ttl_seconds: int = DEFAULT_FAILED_TTL_SECONDS,
        request_timeout: tuple[float, float] = DEFAULT_REQUEST_TIMEOUT,
    ):
        self.root = Path(root)
        self.missing_ttl_seconds = missing_ttl_seconds
        self.failed_ttl_seconds = failed_ttl_seconds
        self.request_timeout = request_timeout
        # Полосы фиксированного размера: один и тот же ключ всегда берёт один
        # и тот же лок, но память не зависит от числа увиденных изображений.
        self._locks = tuple(threading.Lock() for _ in range(LOCK_STRIPES))
        self._in_flight: set[str] = set()
        self._in_flight_guard = threading.Lock()

    def cache_path(self, key: str, source_url: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / f"{digest}{_safe_extension(source_url)}"

    def get(self, key: str, source_url: str) -> CachedImage | None:
        """Возвращает локальный файл, при необходимости скачивая его.

        ``None`` означает, что изображение отсутствует или временно недоступно;
        вызывающая сторона должна показать заглушку. Повторные запросы не
        долбят источник: 404 кешируется маркером ``.missing``, сетевые ошибки —
        коротким маркером ``.failed``.

        Метод блокирующий. HTTP-endpoint использует :meth:`get_or_schedule`.
        """
        cached_path = self.cache_path(key, source_url)
        ready = self._read_ready(cached_path)
        if ready is not None:
            return ready

        missing_marker = _marker_path(cached_path, MISSING_MARKER_SUFFIX)
        if self._is_missing_active(missing_marker):
            return None

        lock = self._lock_for(key)
        with lock:
            # Пока ждали блокировку, файл мог скачать другой поток.
            ready = self._read_ready(cached_path)
            if ready is not None:
                return ready
            if self._is_missing_active(missing_marker):
                return None

            failed_marker = _marker_path(cached_path, FAILED_MARKER_SUFFIX)
            if self._is_failed_active(failed_marker):
                return None

            self._download_and_update_markers(
                source_url, cached_path, missing_marker, failed_marker
            )
            return self._read_ready(cached_path)

    def get_or_schedule(self, key: str, source_url: str) -> tuple[str, CachedImage | None]:
        """Неблокирующий вариант :meth:`get`.

        Возвращает состояние кеша:

        * ``CACHE_STATUS_READY`` — файл уже на диске, можно отдавать;
        * ``CACHE_STATUS_MISSING`` — источник подтвердил 404, нужна заглушка;
        * ``CACHE_STATUS_PENDING`` — файла нет, загрузка поставлена в фон
          (или недавно падала). Пока кеш холодный, клиенту выгоднее отдать
          ссылку на источник напрямую, чем ждать сервер.

        Загрузка дедуплицируется в пределах процесса и не блокирует запрос.
        """
        cached_path = self.cache_path(key, source_url)
        ready = self._read_ready(cached_path)
        if ready is not None:
            return CACHE_STATUS_READY, ready

        missing_marker = _marker_path(cached_path, MISSING_MARKER_SUFFIX)
        if self._is_missing_active(missing_marker):
            return CACHE_STATUS_MISSING, None

        failed_marker = _marker_path(cached_path, FAILED_MARKER_SUFFIX)
        if self._is_failed_active(failed_marker):
            # Недавняя неудача: не долбим источник снова, но и не блокируем
            # браузер — пусть попробует загрузить картинку сам.
            return CACHE_STATUS_PENDING, None

        self._schedule_download(key, source_url, cached_path)
        return CACHE_STATUS_PENDING, None

    def _schedule_download(self, key: str, source_url: str, cached_path: Path) -> None:
        with self._in_flight_guard:
            if key in self._in_flight:
                return
            self._in_flight.add(key)

        try:
            _get_download_executor().submit(
                self._background_download, key, source_url, cached_path
            )
        except Exception as exc:  # noqa: BLE001 - фоновый прогрев не должен ломать запрос
            with self._in_flight_guard:
                self._in_flight.discard(key)
            logger.warning("Failed to schedule image download %s: %s", source_url, exc)

    def _background_download(self, key: str, source_url: str, cached_path: Path) -> None:
        try:
            missing_marker = _marker_path(cached_path, MISSING_MARKER_SUFFIX)
            failed_marker = _marker_path(cached_path, FAILED_MARKER_SUFFIX)
            lock = self._lock_for(key)
            with lock:
                # Пока задача ждала в очереди, файл мог появиться.
                if self._read_ready(cached_path) is not None:
                    return
                if self._is_missing_active(missing_marker):
                    return
                if self._is_failed_active(failed_marker):
                    return
                self._download_and_update_markers(
                    source_url, cached_path, missing_marker, failed_marker
                )
        except Exception as exc:  # noqa: BLE001 - фоновый поток не должен падать молча
            logger.warning("Background image download failed %s: %s", source_url, exc)
        finally:
            with self._in_flight_guard:
                self._in_flight.discard(key)

    def _download_and_update_markers(
        self,
        source_url: str,
        cached_path: Path,
        missing_marker: Path,
        failed_marker: Path,
    ) -> None:
        self._clear_marker(failed_marker)
        try:
            self._download(source_url, cached_path)
        except ImageNotFoundError:
            self._mark_missing(missing_marker)
            logger.debug("Image is missing at source: %s", source_url)
            return
        except Exception as exc:  # noqa: BLE001 - любая ошибка = временная заглушка
            self._mark_failed(failed_marker)
            logger.warning(
                "Failed to cache image %s: %s",
                source_url,
                str(exc) or exc.__class__.__name__,
            )
            return

        self._clear_marker(missing_marker)
        self._clear_marker(failed_marker)

    def _download(self, source_url: str, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)

        response = self._get_session().get(
            source_url,
            stream=True,
            timeout=self.request_timeout,
        )
        try:
            if response.status_code in {404, 410}:
                raise ImageNotFoundError(source_url)
            response.raise_for_status()

            content_type = (
                (response.headers.get("Content-Type") or "")
                .split(";", 1)[0]
                .strip()
                .lower()
            )
            if not content_type.startswith("image/"):
                raise ImageContentTypeError(
                    f"Unexpected Content-Type {content_type!r} for {source_url}"
                )

            temp_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=target.parent,
                    prefix=f".{target.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as temp_file:
                    temp_path = Path(temp_file.name)
                    total_bytes = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if not chunk:
                            continue
                        total_bytes += len(chunk)
                        if total_bytes > MAX_IMAGE_BYTES:
                            raise ImageTooLargeError(
                                f"Image exceeds {MAX_IMAGE_BYTES} bytes: {source_url}"
                            )
                        temp_file.write(chunk)

                if total_bytes == 0:
                    raise ImageContentTypeError(f"Empty image response: {source_url}")

                # Публикуем файл только после полной записи: читатель никогда
                # не увидит частично скачанный файл.
                os.replace(temp_path, target)
                temp_path = None
            finally:
                if temp_path is not None:
                    try:
                        temp_path.unlink(missing_ok=True)
                    except OSError:
                        pass
        finally:
            response.close()

    def _get_session(self) -> requests.Session:
        session = getattr(_session_local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers["User-Agent"] = IMAGE_REQUEST_USER_AGENT
            # Одна повторная попытка для транзиентных 429/5xx. Больше не нужно:
            # фоновая догрузка не критична, а лишние ретраи занимают воркер.
            retry = Retry(
                total=1,
                backoff_factor=0.2,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=("GET",),
            )
            adapter = HTTPAdapter(max_retries=retry)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            _session_local.session = session
        return session

    @staticmethod
    def _read_ready(path: Path) -> CachedImage | None:
        try:
            if not path.is_file() or path.stat().st_size == 0:
                return None
        except OSError:
            return None

        content_type, _ = mimetypes.guess_type(path.name)
        return CachedImage(path=path, content_type=content_type or "image/jpeg")

    def _lock_for(self, key: str) -> threading.Lock:
        # hash() стабилен в пределах процесса — этого достаточно, чтобы один
        # ключ всегда попадал в одну и ту же полосу.
        return self._locks[hash(key) % LOCK_STRIPES]

    def _is_missing_active(self, marker: Path) -> bool:
        if not marker.exists():
            return False

        try:
            is_current_version = marker.read_text(encoding="utf-8").strip() == MISSING_MARKER_VERSION
            is_fresh = time.time() - marker.stat().st_mtime < self.missing_ttl_seconds
        except OSError:
            return False

        if is_current_version and is_fresh:
            return True

        self._clear_marker(marker)
        return False

    def _is_failed_active(self, marker: Path) -> bool:
        if not marker.exists():
            return False

        try:
            is_fresh = time.time() - marker.stat().st_mtime < self.failed_ttl_seconds
        except OSError:
            return False

        if is_fresh:
            return True

        self._clear_marker(marker)
        return False

    def _mark_missing(self, marker: Path) -> None:
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(MISSING_MARKER_VERSION, encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to write missing-image marker %s: %s", marker, exc)

    def _mark_failed(self, marker: Path) -> None:
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch(exist_ok=True)
        except OSError as exc:
            logger.warning("Failed to write failed-image marker %s: %s", marker, exc)

    @staticmethod
    def _clear_marker(marker: Path) -> None:
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            pass


def _marker_path(cached_path: Path, suffix: str) -> Path:
    return cached_path.with_name(cached_path.name + suffix)


def _safe_extension(source_url: str) -> str:
    extension = Path(urlparse(source_url).path).suffix.lower()
    return extension if extension in _SAFE_EXTENSIONS else ".jpg"
