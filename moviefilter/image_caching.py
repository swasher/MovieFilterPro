import os
import threading
import hashlib
import requests
from django.conf import settings
from urllib.parse import urlparse
from pathlib import Path

from .weblogger import log

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
        # cached_dir = Path(settings.MEDIA_ROOT) / "cached_images"
        cached_dir = settings.CACHE_ROOT

        # Ищем имя файла, который связан с этим movie_pk
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
    # Проверяем, нужно ли кэшировать изображение для данного приоритета (для редко используемых приоритетов не кешируем)
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

        cached_filepath = settings.CACHE_ROOT / cached_filename

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
    # Проверяем, нужно ли кэшировать изображение для данного приоритета (для редко используемых приоритетов не кешируем)
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

        # TODO Чисто теоретически, изображения могут быть не только в jpg, а в png, к примеру.

    file_name_hash = hashlib.sha256(image_url.encode()).hexdigest()
    file_extension = os.path.splitext(base_name)[1]
    cached_filename = f"{movie_pk}_{file_name_hash}{file_extension}"  # Используем PK фильма

    cached_filepath = settings.CACHE_ROOT / cached_filename

    # Проверяем, есть ли уже изображение в кэше
    if cached_filepath.exists():
        print(f'CACHE: return cached url {settings.CACHE_URL + cached_filename}')
        return settings.CACHE_URL + cached_filename

    # Изображения нет в кэше, запускаем скачивание в фоне
    threading.Thread(target=download_and_cache_image, args=(image_url, movie_pk, priority)).start()

    # Возвращаем оригинальный URL (как заглушку)
    print(f'CACHE: return original url {image_url}')
    return image_url
