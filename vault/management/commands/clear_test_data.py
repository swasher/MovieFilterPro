from django.core.management.base import BaseCommand
from django.db import transaction

from vault import models as v


class Command(BaseCommand):
    help = 'Удаляет ВСЕ данные только из моделей приложения vault (без затрагивания других приложений).'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('ВНИМАНИЕ: полная очистка данных приложения vault!'))

        # Порядок важен для соблюдения ограничений внешних ключей.
        # Сначала удаляем модели, которые ссылаются на другие (многие-ко-многим, пользовательский контент),
        # затем уже основные сущности.
        to_purge = [
            # Пользовательский контент и связи
            v.Comment,
            v.MovieNote,
            v.Rating,
            v.Review,
            v.FavoritePerson,
            v.UserListMovie,
            v.MoviePerson,

            # Иерархия сериалов
            v.Episode,
            v.Season,

            # Основные модели (после удаления зависимостей)
            v.UserList,
            v.Movie,
            v.Person,
            v.Genre,
        ]

        with transaction.atomic():
            for model in to_purge:
                deleted, _ = model.objects.all().delete()
                self.stdout.write(f'  ✓ {model.__name__}: удалено {deleted}')

        self.stdout.write(self.style.SUCCESS('\n✅ Данные vault очищены. Таблицы других приложений не тронуты.'))
