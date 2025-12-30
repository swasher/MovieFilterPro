from django.core.management.base import BaseCommand
from vault.models import Genre, Country, Movie, Person, MoviePerson
from slugify import slugify
from datetime import date


class Command(BaseCommand):
    help = 'Populate database with sample movie data'

    def handle(self, *args, **options):
        self.stdout.write('Создание тестовых данных...')

        # Жанры
        self.stdout.write('Создание жанров...')
        genres_list = [
            'Драма', 'Комедия', 'Боевик', 'Триллер', 'Фантастика',
            'Ужасы', 'Мелодрама', 'Приключения', 'Детектив', 'Аниме',
            'Мультфильм', 'Вестерн', 'Мюзикл', 'Документальный', 'Криминал'
        ]

        genres = {}
        for genre_name in genres_list:
            genre, created = Genre.objects.get_or_create(
                name=genre_name,
                defaults={'slug': slugify(genre_name, allow_unicode=False)}  # чтобы были только ASCII символы в путях
            )
            genres[genre_name] = genre
            if created:
                self.stdout.write(f'  ✓ Создан жанр: {genre_name}')

        # Страны
        # self.stdout.write('Создание стран...')
        # countries_list = [
        #     ('США', 'US'),
        #     ('Россия', 'RU'),
        #     ('Великобритания', 'GB'),
        #     ('Франция', 'FR'),
        #     ('Япония', 'JP'),
        #     ('Германия', 'DE'),
        #     ('Италия', 'IT'),
        #     ('Испания', 'ES'),
        #     ('Южная Корея', 'KR'),
        #     ('Китай', 'CN'),
        # ]

        # countries = {}
        # for country_name, code in countries_list:
        #     country, created = Country.objects.get_or_create(
        #         name=country_name,
        #         defaults={'code': code}
        #     )
        #     countries[country_name] = country
        #     if created:
        #         self.stdout.write(f'  ✓ Создана страна: {country_name}')



        # Персоны
        self.stdout.write('Создание персон...')
        persons_data = [
            {
                'first_name': 'Кристофер',
                'last_name': 'Нолан',
                'birth_date': date(1970, 7, 30),
                'country': 'Великобритания',
                'gender': 'M',
            },
            {
                'first_name': 'Леонардо',
                'last_name': 'ДиКаприо',
                'birth_date': date(1974, 11, 11),
                'country': 'США',
                'gender': 'M',
            },
            {
                'first_name': 'Квентин',
                'last_name': 'Тарантино',
                'birth_date': date(1963, 3, 27),
                'country': 'США',
                'gender': 'M',
            },
            {
                'first_name': 'Скарлетт',
                'last_name': 'Йоханссон',
                'birth_date': date(1984, 11, 22),
                'country': 'США',
                'gender': 'F',
            },
            {
                'first_name': 'Федор',
                'last_name': 'Бондарчук',
                'birth_date': date(1967, 5, 9),
                'country': 'Россия',
                'gender': 'M',
            },
        ]

        persons = {}
        for person_data in persons_data:
            full_name = f"{person_data['first_name']} {person_data['last_name']}"
            person, created = Person.objects.get_or_create(
                first_name=person_data['first_name'],
                last_name=person_data['last_name'],
                defaults=person_data
            )
            persons[full_name] = person
            if created:
                self.stdout.write(f'  ✓ Создана персона: {full_name}')

        # Фильмы
        self.stdout.write('Создание фильмов...')
        movies_data = [
            {
                'title': 'Начало',
                'original_title': 'Inception',
                'year': 2010,
                'duration': 148,
                'description': 'Кобб – талантливый вор, лучший из лучших в опасном искусстве извлечения: он крадет ценные секреты из глубин подсознания во время сна.',
                'genres': ['Фантастика', 'Боевик', 'Триллер'],
                'countries': ['США', 'Великобритания'],
                'imdb_rating': 8.8,
                'status': 'released',
                'movie_type': 'movie',
                'crew': [
                    {'person': 'Кристофер Нолан', 'role': 'director'},
                    {'person': 'Леонардо ДиКаприо', 'role': 'actor', 'character': 'Дом Кобб'},
                ],
            },
            {
                'title': 'Криминальное чтиво',
                'original_title': 'Pulp Fiction',
                'year': 1994,
                'duration': 154,
                'description': 'Двое бандитов Винсент Вега и Джулс Винфилд ведут философские беседы в перерывах между разборками и решением проблем.',
                'genres': ['Криминал', 'Драма'],
                'countries': ['США'],
                'imdb_rating': 8.9,
                'status': 'released',
                'movie_type': 'movie',
                'crew': [
                    {'person': 'Квентин Тарантино', 'role': 'director'},
                ],
            },
            {
                'title': 'Интерстеллар',
                'original_title': 'Interstellar',
                'year': 2014,
                'duration': 169,
                'description': 'Когда засуха приводит человечество к продовольственному кризису, коллектив исследователей и учёных отправляется сквозь червоточину в путешествие, чтобы превзойти прежние ограничения для космических путешествий человека.',
                'genres': ['Фантастика', 'Драма', 'Приключения'],
                'countries': ['США', 'Великобритания'],
                'imdb_rating': 8.6,
                'status': 'released',
                'movie_type': 'movie',
                'crew': [
                    {'person': 'Кристофер Нолан', 'role': 'director'},
                ],
            },
            {
                'title': 'Темный рыцарь',
                'original_title': 'The Dark Knight',
                'year': 2008,
                'duration': 152,
                'description': 'Бэтмен поднимает ставки в войне с криминалом. С помощью лейтенанта Джима Гордона и прокурора Харви Дента он намерен очистить улицы от преступности.',
                'genres': ['Боевик', 'Криминал', 'Драма'],
                'countries': ['США', 'Великобритания'],
                'imdb_rating': 9.0,
                'status': 'released',
                'movie_type': 'movie',
                'crew': [
                    {'person': 'Кристофер Нолан', 'role': 'director'},
                ],
            },
            {
                'title': 'Притяжение',
                'original_title': None,
                'year': 2017,
                'duration': 132,
                'description': 'После падения НЛО на жилой район Москвы власти оцепили территорию и ввели военное положение.',
                'genres': ['Фантастика', 'Драма'],
                'countries': ['Россия'],
                'imdb_rating': 5.6,
                'status': 'released',
                'movie_type': 'movie',
                'crew': [
                    {'person': 'Федор Бондарчук', 'role': 'director'},
                ],
            },
        ]



        # 1. Собираем все уникальные названия стран из ваших данных о фильмах
        # Например, если movies_data содержит списки ["США", "Россия"]
        all_required_names = set()
        for movie_data in movies_data:
            all_required_names.update(movie_data.get('countries', []))

        # 2. Получаем объекты из БД.
        # Используем name как ключ словаря для быстрого доступа.
        countries_queryset = Country.objects.filter(name__in=all_required_names)
        countries_map = {c.name: c for c in countries_queryset}

        # 3. Проверка на отсутствие (опционально, для отладки)
        missing = all_required_names - set(countries_map.keys())
        if missing:
            self.stdout.write(self.style.WARNING(f' ! Эти страны не найдены в БД: {", ".join(missing)}'))


        for movie_data in movies_data:
            # Извлекаем данные о жанрах, странах и команде
            genre_names = movie_data.pop('genres')
            country_names = movie_data.pop('countries')
            crew_data = movie_data.pop('crew', [])

            # Создаем slug
            if 'slug' not in movie_data:
                movie_data['slug'] = slugify(movie_data['title'], allow_unicode=False)

            # Создаем фильм
            movie, created = Movie.objects.get_or_create(
                title=movie_data['title'],
                year=movie_data['year'],
                defaults=movie_data
            )

            if created:
                self.stdout.write(f'  ✓ Создан фильм: {movie.title} ({movie.year})')

                # Добавляем жанры
                for genre_name in genre_names:
                    if genre_name in genres:
                        movie.genres.add(genres[genre_name])

                # Добавляем страны
                country_names = movie_data.get('countries', [])
                for name in country_names:
                    country_obj = countries_map.get(name)
                    if country_obj:
                        movie.countries.add(country_obj)

                # Добавляем команду
                for crew_member in crew_data:
                    person_name = crew_member['person']
                    if person_name in persons:
                        MoviePerson.objects.get_or_create(
                            movie=movie,
                            person=persons[person_name],
                            role=crew_member['role'],
                            defaults={
                                'character_name': crew_member.get('character', ''),
                            }
                        )
            else:
                self.stdout.write(f'  - Фильм уже существует: {movie.title}')

        self.stdout.write(self.style.SUCCESS('\n✅ База данных успешно заполнена тестовыми данными!'))
        self.stdout.write(self.style.SUCCESS(f'Создано:'))
        self.stdout.write(f'  - Жанров: {Genre.objects.count()}')
        self.stdout.write(f'  - Стран: {Country.objects.count()}')
        self.stdout.write(f'  - Персон: {Person.objects.count()}')
        self.stdout.write(f'  - Фильмов: {Movie.objects.count()}')
