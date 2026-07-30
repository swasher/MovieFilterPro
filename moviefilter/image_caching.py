import os
import threading
import hashlib
import time
import requests
from urllib3.util import Retry
from requests.adapters import HTTPAdapter
from django.conf import settings
from urllib.parse import urlparse, urlunparse
from pathlib import Path

from web_logger import log, LogType

# Глобальный словарь для отслеживания скачиваемых изображений
downloading_images = {}
# Создаем блокировку (mutex) для обеспечения потокобезопасного доступа к downloading_images
downloading_images_lock = threading.Lock()
VALID_PRIORITY = [settings.HIGH, settings.LOW, settings.DEFER]
PLACEHOLDER_IMAGE_PATH = "img/poster-placeholder.svg"
MISSING_MARKER_SUFFIX = ".missing"
FAILED_MARKER_SUFFIX = ".failed"
FAILED_RETRY_SECONDS = 30 * 60  # 30 минут



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


def _mark_image_as_missing(marker_path: Path) -> None:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.touch(exist_ok=True)


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

                        for image_url in list(
                                downloading_images.keys()):  # copy a list, because del may change len of original
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
                                if image_url in downloading_images:
                                    del downloading_images[image_url]
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

    # Проверяем, нужно ли кэшировать изображение для данного приоритета (для редко используемых приоритетов не кешируем)
    if priority not in VALID_PRIORITY:
        log(f"Skipping caching for movie_pk: {movie_pk}, priority: {priority}", LogType.DEBUG)
        return

    # Захватываем блокировку перед тем, как работать с downloading_images
    with downloading_images_lock:
        # Проверяем, скачивается ли уже это изображение (по оригинальному URL).
        if original_image_url in downloading_images:
            return  # Уже скачивается или скачано.

        # Если не скачивается, добавляем его в словарь.
        downloading_images[original_image_url] = True

    log(f"Start downloading: {resolved_image_url}, movie_pk: {movie_pk}", LogType.DEBUG)

    try:
        cached_filename, cached_filepath, missing_marker_path, failed_marker_path = _build_cached_paths(original_image_url, movie_pk)

        # Check if the image is already cached
        if cached_filepath.exists():
            log(f"Already cached: {resolved_image_url}, movie_pk: {movie_pk}", LogType.DEBUG)
            return
        if missing_marker_path.exists():
            log(f"Poster already marked as missing: {resolved_image_url}, movie_pk: {movie_pk}", LogType.DEBUG)
            return

        # Создаем сессию с настройками повтора для временных ошибок
        session = requests.Session()
        # Настройки повтора для временных ошибок (в том числе таймаутов)
        retry_strategy = Retry(
            total=3,  # количество повторных попыток
            backoff_factor=1,  # фактор задержки между попытками
            status_forcelist=[429, 500, 502, 503, 504],  # коды статусов для повтора
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        response = session.get(resolved_image_url, stream=True, timeout=(10, 30))  # connect_timeout=10, read_timeout=30
        response.raise_for_status()  # Raise an exception for bad status codes

        # Create the directory if it doesn't exist
        cached_filepath.parent.mkdir(parents=True, exist_ok=True)
        _clear_missing_marker(missing_marker_path)

        with open(cached_filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

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
        # Удаляем информацию о скачивании изображения из словаря по оригинальному URL
        with downloading_images_lock:
            if original_image_url in downloading_images:
                del downloading_images[original_image_url]


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

    cached_filename, cached_filepath, missing_marker_path, failed_marker_path = _build_cached_paths(image_url, movie_pk)

    # Проверяем, есть ли уже изображение в кэше
    if cached_filepath.exists():
        print(f'CACHE: return cached url {settings.CACHE_URL + cached_filename}')
        return settings.CACHE_URL + cached_filename
    if missing_marker_path.exists():
        return get_placeholder_image_url()
    
    # Проверяем, есть ли маркер ошибки (и если есть, то прошло ли достаточно времени для повторной попытки)
    if failed_marker_path.exists():
        # Проверяем, прошло ли достаточно времени для повторной попытки
        try:
            file_time = failed_marker_path.stat().st_mtime
            current_time = time.time()
            if current_time - file_time < FAILED_RETRY_SECONDS:
                # Пока не прошло достаточно времени, возвращаем зеркало
                resolved_url = resolve_mirror_url(image_url)
                print(f'CACHE: return resolved url {resolved_url} (retry in {FAILED_RETRY_SECONDS - (current_time - file_time)} seconds)')
                return resolved_url
            else:
                # Прошло достаточно времени - удаляем маркер и продолжаем
                _clear_failed_marker(failed_marker_path)
        except Exception as e:
            log(f"Error checking failed marker: {e}", LogType.ERROR)
            # В случае ошибки при проверке маркера - продолжаем с тем же поведением

    # Изображения нет в кэше, запускаем скачивание в фоне (используем оригинальный URL)
    threading.Thread(target=download_and_cache_image, args=(image_url, movie_pk, priority), daemon=True).start()

    # Резолвим URL в зеркало для отображения пользователю
    resolved_url = resolve_mirror_url(image_url)
    print(f'CACHE: return resolved url {resolved_url}')
    return resolved_url
