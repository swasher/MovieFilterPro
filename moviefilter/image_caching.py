import os
import threading
import hashlib
import time
import tempfile
import requests
from urllib3.util import Retry
from requests.adapters import HTTPAdapter
from django.conf import settings
from urllib.parse import urlparse, urlunparse
from pathlib import Path

from web_logger import log, LogType

# Глобальный словарь для отслеживания скачиваемых изображений.
# Ключ включает id фильма: один URL может принадлежать нескольким MovieRSS,
# но у каждой записи свой файл кеша.
downloading_images = {}
# Создаем блокировку (mutex) для обеспечения потокобезопасного доступа к downloading_images
downloading_images_lock = threading.Lock()
VALID_PRIORITY = [settings.HIGH, settings.LOW, settings.DEFER]
PLACEHOLDER_IMAGE_PATH = "img/poster-placeholder.svg"
MISSING_MARKER_SUFFIX = ".missing"
FAILED_MARKER_SUFFIX = ".failed"
FAILED_RETRY_SECONDS = 30
MISSING_RETRY_SECONDS = 24 * 60 * 60

# Версия отрицательного маркера. Маркеры без версии (созданные старым
# загрузчиком) игнорируются, чтобы исправление загрузчика сразу вернуло постеры.
MISSING_MARKER_VERSION = "2"

# Fastpic отдаёт файлы только клиенту с cookie, которую ставит сам сайт.
# Без неё прямой URL постера отвечает 404, хотя на странице просмотра картинка есть.
FASTPIC_DOMAIN = "fastpic.org"
FASTPIC_HOME_URL = "https://fastpic.org/"

# Некоторые хостинги (например, fastpic) отвечают 404 на User-Agent requests,
# даже когда cookie получены. Представляемся обычным браузером.
IMAGE_REQUEST_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/156.0.0.0 Safari/537.36"
)

CACHE_STATUS_READY = "ready"
CACHE_STATUS_PENDING = "pending"
CACHE_STATUS_MISSING = "missing"

_fastpic_cookies: dict[str, str] = {}
_fastpic_cookies_lock = threading.Lock()
_fastpic_prime_lock = threading.Lock()


def get_placeholder_image_url() -> str:
    return f"{settings.STATIC_URL.rstrip('/')}/{PLACEHOLDER_IMAGE_PATH}"


def _build_cached_paths(image_url: str, movie_pk: int) -> tuple[str, Path, Path, Path]:
    parsed_url = urlparse(image_url)
    base_name = Path(parsed_url.path).name
    if not base_name:
        base_name = hashlib.sha256(image_url.encode()).hexdigest() + ".jpg"

    file_name_hash = hashlib.sha256(image_url.encode()).hexdigest()
    file_extension = os.path.splitext(base_name)[1]
    cached_filename = f"{movie_pk}_{file_name_hash}{file_extension}"
    cached_filepath = settings.CACHE_ROOT / cached_filename
    missing_marker_path = cached_filepath.with_name(cached_filepath.name + MISSING_MARKER_SUFFIX)
    failed_marker_path = cached_filepath.with_name(cached_filepath.name + FAILED_MARKER_SUFFIX)
    return cached_filename, cached_filepath, missing_marker_path, failed_marker_path


def get_cached_image_state(image_url: str | None, movie_pk: int, priority: int) -> tuple[str, Path | None]:
    """Возвращает состояние локального кеша и запускает скачивание при необходимости."""
    if not image_url:
        return CACHE_STATUS_MISSING, None

    _, cached_filepath, missing_marker_path, failed_marker_path = _build_cached_paths(image_url, movie_pk)
    if cached_filepath.exists():
        return CACHE_STATUS_READY, cached_filepath
    if _has_active_missing_marker(missing_marker_path):
        return CACHE_STATUS_MISSING, None

    if failed_marker_path.exists():
        try:
            if time.time() - failed_marker_path.stat().st_mtime < FAILED_RETRY_SECONDS:
                return CACHE_STATUS_PENDING, None
            _clear_failed_marker(failed_marker_path)
        except OSError as exc:
            log(f"Error checking failed marker: {exc}", LogType.ERROR)
            return CACHE_STATUS_PENDING, None

    download_key = (movie_pk, image_url)
    with downloading_images_lock:
        is_downloading = download_key in downloading_images
    if not is_downloading:
        threading.Thread(target=download_and_cache_image, args=(image_url, movie_pk, priority), daemon=True).start()

    return CACHE_STATUS_PENDING, None


def _mark_image_as_missing(marker_path: Path) -> None:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(MISSING_MARKER_VERSION, encoding="utf-8")


def _has_active_missing_marker(marker_path: Path) -> bool:
    """
    Проверяет, можно ли доверять маркеру отсутствия изображения.

    Маркер считается активным, только если он создан текущей версией загрузчика
    и не истёк срок повторной проверки. Устаревшие и чужие маркеры удаляются.
    """
    if not marker_path.exists():
        return False

    try:
        is_current_version = marker_path.read_text(encoding="utf-8").strip() == MISSING_MARKER_VERSION
        is_fresh = time.time() - marker_path.stat().st_mtime < MISSING_RETRY_SECONDS
    except OSError as exc:
        log(f"Error checking missing marker: {exc}", LogType.ERROR)
        return False

    if is_current_version and is_fresh:
        return True

    _clear_missing_marker(marker_path)
    return False


def _mark_image_as_failed(marker_path: Path) -> None:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.touch(exist_ok=True)


def _clear_missing_marker(marker_path: Path) -> None:
    try:
        marker_path.unlink(missing_ok=True)
    except TypeError:
        if marker_path.exists():
            marker_path.unlink()


def _clear_failed_marker(marker_path: Path) -> None:
    try:
        marker_path.unlink(missing_ok=True)
    except TypeError:
        if marker_path.exists():
            marker_path.unlink()


def resolve_mirror_url(image_url: str) -> str:
    parsed = urlparse(image_url)
    domain = parsed.netloc
    if domain in getattr(settings, "SOURCE_MIRRORS", {}):
        mirror = settings.SOURCE_MIRRORS[domain]
        parsed = parsed._replace(netloc=mirror)
        return urlunparse(parsed)
    return image_url


def _is_fastpic_url(image_url: str) -> bool:
    host = (urlparse(image_url).hostname or "").lower()
    return host == FASTPIC_DOMAIN or host.endswith(f".{FASTPIC_DOMAIN}")


def _apply_cached_fastpic_cookies(session: requests.Session) -> bool:
    with _fastpic_cookies_lock:
        cookies = dict(_fastpic_cookies)

    if not cookies:
        return False

    for name, value in cookies.items():
        session.cookies.set(name, value, domain=f".{FASTPIC_DOMAIN}", path="/")
    return True


def _prime_fastpic_session(session: requests.Session) -> bool:
    """Получает cookie fastpic с главной страницы, чтобы прямой URL отдал файл."""
    try:
        response = session.get(FASTPIC_HOME_URL, timeout=(10, 30))
    except requests.exceptions.RequestException as exc:
        log(f"Failed to prime fastpic session: {exc}", LogType.ERROR)
        return False

    if response.status_code >= 400:
        log(f"Failed to prime fastpic session: HTTP {response.status_code}", LogType.ERROR)
        return False

    cookies = {
        cookie.name: cookie.value
        for cookie in session.cookies
        if cookie.domain.endswith(FASTPIC_DOMAIN)
    }
    if not cookies:
        log("Fastpic session has no cookies after priming", LogType.ERROR)
        return False

    with _fastpic_cookies_lock:
        _fastpic_cookies.clear()
        _fastpic_cookies.update(cookies)
    return True


def _ensure_fastpic_cookies(session: requests.Session) -> bool:
    """Возвращает cookie fastpic, получая их один раз на процесс."""
    if _apply_cached_fastpic_cookies(session):
        return True

    # Пока один поток получает cookie, остальные ждут и используют результат.
    with _fastpic_prime_lock:
        if _apply_cached_fastpic_cookies(session):
            return True
        return _prime_fastpic_session(session)


def _refresh_fastpic_cookies(session: requests.Session) -> bool:
    with _fastpic_prime_lock:
        return _prime_fastpic_session(session)


def _fetch_image_response(session: requests.Session, image_url: str):
    """
    Запрашивает изображение.

    Для fastpic заранее получает cookie, а при 403/404 один раз обновляет их
    и повторяет запрос. Возвращает ответ и признак того, что cookie fastpic
    доступны.
    """
    is_fastpic = _is_fastpic_url(image_url)
    fastpic_ready = _ensure_fastpic_cookies(session) if is_fastpic else True

    response = session.get(image_url, stream=True, timeout=(10, 30))
    if is_fastpic and response.status_code in {403, 404}:
        response.close()
        fastpic_ready = _refresh_fastpic_cookies(session)
        response = session.get(image_url, stream=True, timeout=(10, 30))

    return response, is_fastpic, fastpic_ready


def remove_cached_image(movie_pk):
    """
    Удаляет закешированное изображение по movie_pk.
    Потокобезопасная функция.
    """
    log(f"Trying to remove cached image by movie_pk: {movie_pk}", LogType.DEBUG)
    try:
        # cached_dir = Path(settings.MEDIA_ROOT) / "cached_images"
        cached_dir = settings.CACHE_ROOT

        # Ищем имя файла, который связан с этим movie_pk
        for filename in os.listdir(cached_dir):
            if filename.startswith(f"{movie_pk}_"):
                cached_filepath = cached_dir / filename
                marker_filepath = cached_dir / f"{filename}{MISSING_MARKER_SUFFIX}"
                failed_marker_filepath = cached_dir / f"{filename}{FAILED_MARKER_SUFFIX}"
                try:
                    os.remove(cached_filepath)
                    log(f"Removed cached image: {cached_filepath}", LogType.DEBUG)
                except FileNotFoundError:
                    log(f"Cached image not found (already removed?): {cached_filepath}", LogType.DEBUG)
                except Exception as e:
                    log(f"Error removing cached image: {e}", LogType.ERROR)
                try:
                    marker_filepath.unlink(missing_ok=True)
                except TypeError:
                    if marker_filepath.exists():
                        marker_filepath.unlink()
                try:
                    failed_marker_filepath.unlink(missing_ok=True)
                except TypeError:
                    if failed_marker_filepath.exists():
                        failed_marker_filepath.unlink()
                finally:
                    # В любом случае - удаляем из downloading_images
                    with downloading_images_lock:
                        # Если это изображение скачивалось, то найдем его в downloading_images по части имени

                        for download_key in list(
                                downloading_images.keys()):  # copy a list, because del may change len of original
                            downloading_movie_pk, image_url = download_key
                            if downloading_movie_pk != movie_pk:
                                continue
                            # Generate a unique filename based on the image URL
                            parsed_url = urlparse(image_url)
                            base_name = Path(parsed_url.path).name
                            if not base_name:
                                base_name = hashlib.sha256(
                                    image_url.encode()).hexdigest() + ".jpg"  # fallback for base name

                            file_name_hash = hashlib.sha256(image_url.encode()).hexdigest()
                            file_extension = os.path.splitext(base_name)[1]
                            cached_filename = f"{movie_pk}_{file_name_hash}{file_extension}"
                            if cached_filename == filename:
                                if download_key in downloading_images:
                                    del downloading_images[download_key]
                                    log(f"Removed from downloading_images: {image_url}", LogType.DEBUG)
                                    break  # удалили - выходим из цикла.

    except FileNotFoundError:
        log(f"Cached image dir not found.", LogType.DEBUG)
    except Exception as e:
        log(f"Error in remove_cached_image: {e}", LogType.ERROR)


def download_and_cache_image(image_url, movie_pk, priority):
    """
    Скачивает и кэширует изображение.
    Потокобезопасная функция.
    """
    # Используем оригинальный URL для ключей и имен файлов, чтобы избежать несоответствий
    original_image_url = image_url
    resolved_image_url = resolve_mirror_url(original_image_url)
    download_key = (movie_pk, original_image_url)
    temporary_filepath = None

    # Захватываем блокировку перед тем, как работать с downloading_images
    with downloading_images_lock:
        # Проверяем, скачивается ли уже этот файл.
        if download_key in downloading_images:
            return  # Уже скачивается или скачано.

        # Если не скачивается, добавляем его в словарь.
        downloading_images[download_key] = True

    log(f"Start downloading: {resolved_image_url}, movie_pk: {movie_pk}", LogType.DEBUG)

    try:
        cached_filename, cached_filepath, missing_marker_path, failed_marker_path = _build_cached_paths(original_image_url, movie_pk)

        # Check if the image is already cached
        if cached_filepath.exists():
            log(f"Already cached: {resolved_image_url}, movie_pk: {movie_pk}", LogType.DEBUG)
            return
        if _has_active_missing_marker(missing_marker_path):
            log(f"Poster already marked as missing: {resolved_image_url}, movie_pk: {movie_pk}", LogType.DEBUG)
            return

        # Создаем сессию с настройками повтора для временных ошибок
        session = requests.Session()
        session.headers["User-Agent"] = IMAGE_REQUEST_USER_AGENT
        # Настройки повтора для временных ошибок (в том числе таймаутов)
        retry_strategy = Retry(
            total=3,  # количество повторных попыток
            backoff_factor=1,  # фактор задержки между попытками
            status_forcelist=[429, 500, 502, 503, 504],  # коды статусов для повтора
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        response, is_fastpic, fastpic_ready = _fetch_image_response(session, resolved_image_url)
        if is_fastpic and not fastpic_ready and response.status_code in {403, 404, 410}:
            # Без cookie fastpic отвечает 404 на существующие файлы: это не повод
            # помечать постер отсутствующим навсегда.
            raise requests.exceptions.RequestException(
                f"Fastpic returned HTTP {response.status_code} without a session cookie"
            )
        response.raise_for_status()  # Raise an exception for bad status codes

        # Create the directory if it doesn't exist
        cached_filepath.parent.mkdir(parents=True, exist_ok=True)
        _clear_missing_marker(missing_marker_path)

        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=cached_filepath.parent,
            prefix=f".{cached_filename}.",
            suffix=".tmp",
            delete=False,
        ) as f:
            temporary_filepath = Path(f.name)
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        # Файл становится доступен обработчику постера только после полной записи.
        os.replace(temporary_filepath, cached_filepath)
        temporary_filepath = None
        _clear_failed_marker(failed_marker_path)
        log(f"Downloaded and cached: {resolved_image_url}, movie_pk: {movie_pk}", LogType.DEBUG)

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else None
        if status_code in {404, 410}:
            _mark_image_as_missing(missing_marker_path)
            log(
                f"Poster not found, using placeholder instead: {resolved_image_url}, movie_pk: {movie_pk}",
                LogType.DEBUG,
            )
        else:
            # Для других HTTP ошибок помечаем как "failed" вместо "missing"
            _mark_image_as_failed(failed_marker_path)
            log(f"Error downloading image (marked as failed): {e}", LogType.ERROR)
    except requests.exceptions.ReadTimeout:
        # Таймаут на чтении - помечаем как "failed"
        _mark_image_as_failed(failed_marker_path)
        log(f"Read timeout downloading image (marked as failed): {resolved_image_url}, movie_pk: {movie_pk}", LogType.ERROR)
    except requests.exceptions.ConnectTimeout:
        # Таймаут на подключение - помечаем как "failed"
        _mark_image_as_failed(failed_marker_path)
        log(f"Connect timeout downloading image (marked as failed): {resolved_image_url}, movie_pk: {movie_pk}", LogType.ERROR)
    except requests.exceptions.RequestException as e:
        # Для других ошибок запросов помечаем как "failed" вместо "missing"
        _mark_image_as_failed(failed_marker_path)
        log(f"Error downloading image (marked as failed): {e}", LogType.ERROR)
    finally:
        if temporary_filepath:
            try:
                temporary_filepath.unlink(missing_ok=True)
            except OSError:
                pass
        # Удаляем информацию о скачивании изображения из словаря по оригинальному URL
        with downloading_images_lock:
            if download_key in downloading_images:
                del downloading_images[download_key]


def get_cached_image_url(image_url, movie_pk, priority):
    """
    Проверяет, закешировано ли изображение локально.
    Если нет, то возвращает URL с зеркалом и запускает скачивание в фоне.
    Возвращает URL к изображению.
    """
    # Проверяем, нужно ли кэшировать изображение для данного приоритета (для редко используемых приоритетов не кешируем)
    if priority not in VALID_PRIORITY:
        log(f"Skipping getting cached image url, movie_pk: {movie_pk}, priority: {priority}", LogType.DEBUG)
        return image_url  # Изображение не нужно кешировать, возвращаем оригинальный URL

    if not image_url:
        return get_placeholder_image_url()

    status, cached_filepath = get_cached_image_state(image_url, movie_pk, priority)
    if status == CACHE_STATUS_READY and cached_filepath is not None:
        return settings.CACHE_URL + cached_filepath.name
    if status == CACHE_STATUS_MISSING:
        return get_placeholder_image_url()

    return resolve_mirror_url(image_url)
