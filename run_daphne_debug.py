import os
import sys
import django
from daphne.cli import CommandLineInterface

if __name__ == "__main__":
    # Установка модуля настроек Django (замените 'your_project.settings' на ваш)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "movie_filter_pro.settings")

    # Аргументы командной строки для Daphne (аналогично 'daphne your_project.asgi:application -p 8000')
    sys.argv = [
        "daphne",  # Имя команды
        "movie_filter_pro.asgi:application",  # Путь к ASGI-приложению (из asgi.py)
        "-p",
        "8000",  # Порт (можно изменить)
        "-b",
        "127.0.0.1",  # Хост (localhost)
        "--verbosity",
        "1",  # Уровень логирования (опционально, для DEBUG)
    ]

    # Инициализация Django
    django.setup()

    # Запуск Daphne
    CommandLineInterface.entrypoint()
