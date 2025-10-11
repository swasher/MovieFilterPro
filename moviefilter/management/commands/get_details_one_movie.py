from dataclasses import fields
from django.core.management.base import BaseCommand

from moviefilter.parse import get_details
from moviefilter.classes import KinozalMovie


class Command(BaseCommand):
    help = "Сканирует определенную страницу Кинозала (нужно для дебага)"

    def add_arguments(self, parser):
        parser.add_argument("id", type=int, help="Movie id")

    def handle(self, *args, **options):
        # Логика вашей команды
        kinozal_id = options["id"]

        self.stdout.write(f"Выполняется парсинг фильма с id: {kinozal_id}")

        # self.stdout.write(self.style.SUCCESS("Команда успешно выполнена!"))

        # Выполняется get_details над ссылкой https://kinozal.guru/details.php?id=<id>
        movie = KinozalMovie()
        movie.kinozal_id = kinozal_id
        get_details(movie)
        print(f"{KinozalMovie.__name__}:\n" + "\n".join(f"  {f.name}: {getattr(movie, f.name)}" for f in fields(KinozalMovie)))
