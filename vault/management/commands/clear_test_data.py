from django.core.management.base import BaseCommand
from vault.models import Genre, Country, Movie, Person, MoviePerson


class Command(BaseCommand):
    help = 'Удаляет ВСЕ данные из таблиц каталога (Movie, Person, Genre, Country, MoviePerson)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('ВНИМАНИЕ: Выполняется полная очистка таблиц каталога!'))

        # Удаляем данные. Порядок важен для логирования, хотя Django CASCADE обработает зависимости.
        # Мы удаляем только данные из моделей, задействованных в populate_movies.py

        # 1. Связи персон с фильмами
        count_mp, _ = MoviePerson.objects.all().delete()
        self.stdout.write(f'  ✓ Удалено связей (MoviePerson): {count_mp}')

        # 2. Фильмы
        count_m, _ = Movie.objects.all().delete()
        self.stdout.write(f'  ✓ Удалено фильмов (Movie): {count_m}')

        # 3. Персоны
        count_p, _ = Person.objects.all().delete()
        self.stdout.write(f'  ✓ Удалено персон (Person): {count_p}')

        # 4. Жанры
        count_g, _ = Genre.objects.all().delete()
        self.stdout.write(f'  ✓ Удалено жанров (Genre): {count_g}')

        self.stdout.write(self.style.SUCCESS('\n✅ База данных успешно очищена от тестовых данных каталога!'))
