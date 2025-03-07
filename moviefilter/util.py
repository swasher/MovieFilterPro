import os
import logging
import requests
import hashlib
import threading
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from urllib.parse import urlparse
from pathlib import Path
from django.conf import settings

# logger = logging.getLogger('my_logger')
channel_layer = get_channel_layer()

debug_logger = logging.getLogger('debug_logger')
scan_logger = logging.getLogger('scan_logger')

def is_float(string):
    if string.replace(".", "").isnumeric():
        return True
    else:
        return False


def year_to_int(year: str) -> int:
    try:
        year = int(year)
    except ValueError:
        raise Exception('Year not int')
    return year


def get_object_or_none(klass, *args, **kwargs):
    """
    Use get() to return an object, or returns None if the object
    does not exist instead of throwing an exception.
    klass may be a Model, Manager, or QuerySet object. All other passed
    arguments and keyword arguments are used in the get() query.
    Like with QuerySet.get(), MultipleObjectsReturned is raised if more than
    one object is found.
    """
    queryset = klass._default_manager.all() if hasattr(klass, "_default_manager") else klass
    if not hasattr(queryset, "get"):
        klass__name = (
            klass.__name__ if isinstance(klass, type) else klass.__class__.__name__
        )
        raise ValueError(
            "First argument to get_object_or_none() must be a Model, Manager, "
            "or QuerySet, not '%s'." % klass__name
        )
    try:
        return queryset.get(*args, **kwargs)
    except queryset.model.DoesNotExist:
        return None


def not_match_rating(movie_rating: float | None, filter_rating: float | None) -> bool:
    """
    Возвращает True, если рейтинг фильмы ниже заданного.
    Если у фильма нет рейтинга, то фильм проходит проверку (возв. False)
    """
    if movie_rating:
        if movie_rating < filter_rating:
            return True
    return False


def send_log_to_websocket(log_message):
    async_to_sync(channel_layer.group_send)(
        "log_updates",
        {
            "type": "send_log_update",  # Это имя метода, который будет вызван в LogConsumer
            "content": log_message,
        },
    )


def log(message: str, logger_name: str = 'scan'):
    """
    Logs a message to a specific log file AND to web-socket.

    Args:
        message: The message to log.
        logger_name: The name of the logger to use ('debug' or 'scan'). Defaults to 'debug'.
        show_log_level: Whether to include the log level in the message sent to the WebSocket.
    """
    if logger_name == 'debug':
        log_level = 'DEBUG'
        debug_logger.debug(message)
    elif logger_name == 'scan':
        log_level = 'INFO'
        scan_logger.info(message)
    elif logger_name == 'error':
        log_level = 'ERROR'
        logging.getLogger('django').error(message)  # this line will add error message to django errors
    else:
        log_level = 'ERROR'
        raise ValueError("Invalid logger_name. Must be 'debug' or 'scan' or 'error'.")

    # log_level нужно добавлять, чтобы различать scan и debug сообщения на стороне фронта. Там эта часть удаляется.
    log_message = f"{log_level}: {message}"
    send_log_to_websocket(log_message)


# Глобальный словарь для отслеживания скачиваемых изображений
downloading_images = {}
# Создаем блокировку (mutex) для обеспечения потокобезопасного доступа к downloading_images
downloading_images_lock = threading.Lock()
VALID_PRIORITY = [settings.HIGH, settings.LOW, settings.DEFER]


def remove_cached_image(movie_pk):
    """
    Удаляет закешированное изображение по movie_pk.
    Потокобезопасная функция.
    """
    log(f"Trying to remove cached image by movie_pk: {movie_pk}", 'debug')
    try:
        # Ищем имя файла, который связан с этим movie_pk
        cached_dir = Path(settings.MEDIA_ROOT) / "cached_images"
        for filename in os.listdir(cached_dir):
            if filename.startswith(f"{movie_pk}_"):
                cached_filepath = cached_dir / filename
                try:
                    os.remove(cached_filepath)
                    log(f"Removed cached image: {cached_filepath}", 'debug')
                except FileNotFoundError:
                    log(f"Cached image not found (already removed?): {cached_filepath}", 'debug')
                except Exception as e:
                    log(f"Error removing cached image: {e}", 'error')
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
                                    log(f"Removed from downloading_images: {image_url}", 'debug')
                                    break  # удалили - выходим из цикла.

    except FileNotFoundError:
        log(f"Cached image dir not found.", 'debug')
    except Exception as e:
        log(f"Error in remove_cached_image: {e}", 'error')


def download_and_cache_image(image_url, movie_pk, priority):
    """
    Скачивает и кэширует изображение.
    Потокобезопасная функция.
    """
    # Проверяем, нужно ли кэшировать изображение для данного приоритета
    if priority not in VALID_PRIORITY:
        log(f"Skipping caching for movie_pk: {movie_pk}, priority: {priority}", 'debug')
        return

    # Захватываем блокировку перед тем, как работать с downloading_images
    with downloading_images_lock:
        # Проверяем, скачивается ли уже это изображение.
        if image_url in downloading_images:
            return  # Уже скачивается или скачано.

        # Если не скачивается, добавляем его в словарь.
        # Это сигнализирует другим потокам, что изображение сейчас скачивается.
        downloading_images[image_url] = True

    log(f"Start downloading: {image_url}, movie_pk: {movie_pk}", 'debug')

    try:
        # Generate a unique filename based on the image URL
        parsed_url = urlparse(image_url)
        base_name = Path(parsed_url.path).name
        if not base_name:
            base_name = hashlib.sha256(image_url.encode()).hexdigest() + ".jpg"  # fallback for base name

        file_name_hash = hashlib.sha256(image_url.encode()).hexdigest()
        file_extension = os.path.splitext(base_name)[1]
        cached_filename = f"{movie_pk}_{file_name_hash}{file_extension}"  # Используем PK фильма

        cached_filepath = Path(settings.MEDIA_ROOT) / "cached_images" / cached_filename

        # Check if the image is already cached
        if cached_filepath.exists():
            log(f"Already cached: {image_url}, movie_pk: {movie_pk}", 'debug')
            return

        response = requests.get(image_url, stream=True, timeout=5)  # added timeout
        response.raise_for_status()  # Raise an exception for bad status codes

        # Create the directory if it doesn't exist
        cached_filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(cached_filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        log(f"Downloaded and cached: {image_url}, movie_pk: {movie_pk}", 'debug')

    except requests.exceptions.RequestException as e:
        log(f"Error downloading image: {e}", 'error')
    finally:
        # В блоке finally, который всегда выполняется,
        # удаляем информацию о скачивании изображения из словаря.
        # Это делается, чтобы другие потоки могли снова начать скачивание,
        # если это потребуется в будущем.
        with downloading_images_lock:
            if image_url in downloading_images:
                del downloading_images[image_url]


def get_cached_image_url(image_url, movie_pk, priority):
    """
    Проверяет, закешировано ли изображение локально.
    Если нет, то возвращает исходный URL, но запускает скачивание в фоне.
    Возвращает URL к изображению.
    """
    # Проверяем, нужно ли кэшировать изображение для данного приоритета
    if priority not in VALID_PRIORITY:
        log(f"Skipping getting cached image url, movie_pk: {movie_pk}, priority: {priority}", 'debug')
        return image_url  # Изображение не нужно кешировать, возвращаем оригинальный URL

    if not image_url:
        return None  # Обработка пустого image_url

    # Generate a unique filename based on the image URL
    parsed_url = urlparse(image_url)
    base_name = Path(parsed_url.path).name
    if not base_name:
        base_name = hashlib.sha256(image_url.encode()).hexdigest() + ".jpg"  # fallback for base name

    file_name_hash = hashlib.sha256(image_url.encode()).hexdigest()
    file_extension = os.path.splitext(base_name)[1]
    cached_filename = f"{movie_pk}_{file_name_hash}{file_extension}"  # Используем PK фильма

    cached_filepath = Path(settings.MEDIA_ROOT) / "cached_images" / cached_filename

    # Проверяем, есть ли уже изображение в кэше
    if cached_filepath.exists():
        return settings.MEDIA_URL + "cached_images/" + cached_filename

    # Изображения нет в кэше, запускаем скачивание в фоне
    threading.Thread(target=download_and_cache_image, args=(image_url, movie_pk, priority)).start()

    # Возвращаем оригинальный URL (как заглушку)
    return image_url
