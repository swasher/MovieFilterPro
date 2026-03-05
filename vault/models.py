from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from slugify import slugify
from django.conf import settings

import core


def _build_tmdb_image_url(raw_path: str | None, size: str) -> str | None:
    if not raw_path:
        return None
    value = str(raw_path).strip()
    if not value:
        return None

    if value.startswith('http://') or value.startswith('https://'):
        return value

    base_url = getattr(settings, 'TMDB_IMAGE_BASE_URL', 'https://image.tmdb.org/t/p/')
    if not base_url.endswith('/'):
        base_url += '/'

    normalized_size = str(size or 'w500').strip('/') or 'w500'
    normalized_path = value if value.startswith('/') else f'/{value}'
    return f'{base_url}{normalized_size}{normalized_path}'


class Person(models.Model):
    """Модель для актеров, режиссеров и других людей"""
    GENDER_CHOICES = [
        ('M', 'Мужской'),
        ('F', 'Женский'),
    ]

    tmdb_id = models.CharField(max_length=10, unique=True)
    imdb_id = models.CharField(max_length=10, unique=True)
    name = models.CharField('Имя-Фимилия (RU)', max_length=100)
    original_name = models.CharField('Имя-Фимилия (EN)', max_length=100)
    birth_date = models.DateField('Дата рождения', null=True, blank=True)
    death_date = models.DateField('Дата смерти', null=True, blank=True)
    gender = models.CharField('Пол', max_length=1, choices=GENDER_CHOICES, blank=True)
    # photo = models.ImageField('Фото', upload_to='persons/', null=True, blank=True)
    photo = models.CharField('Путь к фото', max_length=255, blank=True, null=True, help_text='Относительный путь к фото (например: /pynwU6PGLAdDE840rC9m6jEahWg.jpg)')
    biography = models.TextField('Биография', blank=True)
    # country = models.CharField('Страна', max_length=100, blank=True)
    country = models.ForeignKey('core.Country', on_delete=models.RESTRICT)

    class Meta:
        verbose_name = 'Персона'
        verbose_name_plural = 'Персоны'
        ordering = ['name']

    def __str__(self):
        return f"{self.name}"

    @property
    def photo_url(self):
        """Генерируем полный URL на лету"""
        default_size = getattr(settings, 'TMDB_IMAGE_SIZE', 'w500')
        return _build_tmdb_image_url(self.photo, default_size)

    def get_photo_url(self, size='w500'):
        """Метод для получения URL с конкретным размером"""
        return _build_tmdb_image_url(self.photo, size)


class Genre(models.Model):
    """Модель жанров фильмов"""
    name = models.CharField('Название', max_length=50, unique=True)
    slug = models.SlugField('URL', unique=True, blank=True)

    class Meta:
        verbose_name = 'Жанр'
        verbose_name_plural = 'Жанры'
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or 'genre'
            slug = base_slug
            counter = 2
            while Genre.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base_slug}-{counter}'
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name



class Movie(models.Model):
    """Основная модель фильма"""
    class Status(models.TextChoices):
        ANNOUNCED = 'announced', 'Анонсирован'
        PRODUCTION = 'production', 'В производстве'
        POST_PRODUCTION = 'post_production', 'Пост-продакшн'
        RELEASED = 'released', 'Вышел'
        COMPLETED = 'completed', 'Завершен'
        HIATUS = 'hiatus', 'Пауза'
        CANCELLED = 'cancelled', 'Отменен'

    class MovieType(models.TextChoices):
        MOVIE = 'movie', 'Фильм'
        SERIES = 'series', 'Сериал'
        CARTOON = 'cartoon', 'Мультфильм'
        ANIME = 'anime', 'Аниме'
        SHOW = 'show', 'Шоу'

    class Source(models.TextChoices):
        KINORIUM = 'kinorium', 'Kinorium'
        TMDB = 'tmdb', 'TMDB'

    class TMDBMediaType(models.TextChoices):
        MOVIE = 'movie', 'Movie'
        TV = 'tv', 'TV'

    title = models.CharField('Название', max_length=255)
    original_title = models.CharField('Оригинальное название', max_length=255, blank=True, null=True)
    slug = models.SlugField('URL', unique=True, blank=True)
    description = models.TextField('Описание', blank=True)

    year = models.PositiveIntegerField('Год выпуска', null=True, blank=True)
    is_ongoing = models.BooleanField('Выходит сейчас', default=False)
    year_end = models.PositiveIntegerField('Год окончания', null=True, blank=True)

    duration = models.PositiveIntegerField('Длительность (мин)', null=True, blank=True)
    release_date = models.DateField('Дата выхода', null=True, blank=True)

    movie_type = models.CharField('Тип', max_length=20, choices=MovieType, default=MovieType.MOVIE)
    status = models.CharField('Статус', max_length=20, choices=Status, default=Status.RELEASED)

    # poster = models.ImageField('Постер', upload_to='posters/', null=True, blank=True)
    poster = models.CharField('Путь к постеру', max_length=255, blank=True, null=True, help_text='Относительный путь к фото (например: /pynwU6PGLAdDE840rC9m6jEahWg.jpg)')
    trailer_url = models.URLField('Ссылка на трейлер', blank=True)

    genres = models.ManyToManyField(Genre, verbose_name='Жанры', related_name='movies')
    countries = models.ManyToManyField('core.Country', verbose_name='Страны', related_name='movies')

    age_rating = models.CharField('Возрастной рейтинг', max_length=10, blank=True)
    budget = models.DecimalField('Бюджет', max_digits=12, decimal_places=2, null=True, blank=True)
    box_office = models.DecimalField('Сборы', max_digits=12, decimal_places=2, null=True, blank=True)

    imdb_rating = models.DecimalField('Рейтинг IMDb', max_digits=3, decimal_places=1, null=True, blank=True)
    imdb_votes = models.PositiveIntegerField('Голосов IMDb', null=True, blank=True)

    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    source = models.CharField(
        'Источник',
        max_length=20,
        choices=Source,
        default=Source.KINORIUM,
    )
    tmdb_id = models.PositiveIntegerField('TMDB ID', null=True, blank=True, db_index=True)
    tmdb_media_type = models.CharField(
        'TMDB тип',
        max_length=10,
        choices=TMDBMediaType,
        null=True,
        blank=True,
    )
    tmdb_last_synced_at = models.DateTimeField('Последняя синхронизация TMDB', null=True, blank=True)

    # Для сериалов:
    seasons_count = models.PositiveIntegerField('Количество сезонов', null=True, blank=True)
    episodes_count = models.PositiveIntegerField('Количество эпизодов', null=True, blank=True)

    class Meta:
        verbose_name = 'Фильм'
        verbose_name_plural = 'Фильмы'
        ordering = ['-year', 'title']
        indexes = [
            models.Index(fields=['-year', 'title']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.title} ({self.year})" if self.year else self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def get_year_display(self):
        if self.movie_type != 'series':
            return str(self.year) if self.year else 'Неизвестно'

        if not self.year:
            return 'Неизвестно'

        if self.is_ongoing:
            return f"{self.year}–..."
        elif self.year_end:
            return f"{self.year}–{self.year_end}"
        else:
            return str(self.year)

    def get_average_rating(self):
        """Средний рейтинг от пользователей"""
        ratings = self.user_movies.exclude(rating__isnull=True)
        if ratings:
            return sum(r.rating for r in ratings) / len(ratings)
        return None

    @property
    def poster_url(self):
        default_size = getattr(settings, 'TMDB_IMAGE_SIZE', 'w500')
        return _build_tmdb_image_url(self.poster, default_size)

    def get_poster_url(self, size='w500'):
        return _build_tmdb_image_url(self.poster, size)

    def get_directors(self):
        return self.movie_persons.filter(role='director')

    def get_actors(self):
        return self.movie_persons.filter(role='actor')


class Season(models.Model):
    """Сезон сериала"""
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='seasons')
    season_number = models.PositiveIntegerField('Номер сезона')
    title = models.CharField('Название', max_length=255, blank=True)
    description = models.TextField('Описание', blank=True)
    note = models.TextField('Заметка', blank=True)
    source = models.CharField(
        'Источник',
        max_length=20,
        choices=Movie.Source,
        default=Movie.Source.KINORIUM,
    )
    release_date = models.DateField('Дата выхода', null=True, blank=True)
    # poster = models.ImageField('Постер', upload_to='seasons/', null=True, blank=True)
    poster = models.CharField('Путь к постеру', max_length=255, blank=True, null=True, help_text='Относительный путь к фото (например: /pynwU6PGLAdDE840rC9m6jEahWg.jpg)')


    class Meta:
        ordering = ['season_number']
        unique_together = ['movie', 'season_number']


class Episode(models.Model):
    """Эпизод сезона"""
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='episodes')
    episode_number = models.PositiveIntegerField('Номер эпизода')
    title = models.CharField('Название', max_length=255)
    description = models.TextField('Описание', blank=True)
    duration = models.PositiveIntegerField('Длительность (мин)', null=True, blank=True)
    release_date = models.DateField('Дата выхода', null=True, blank=True)

    class Meta:
        ordering = ['episode_number']
        unique_together = ['season', 'episode_number']


class MoviePerson(models.Model):
    """Связь фильмов с персонами (актеры, режиссеры и т.д.)"""
    ROLE_CHOICES = [
        ('actor', 'Актер'),
        ('director', 'Режиссер'),
        ('producer', 'Продюсер'),
        ('writer', 'Сценарист'),
        ('composer', 'Композитор'),
        ('operator', 'Оператор'),
        ('editor', 'Монтажер'),
    ]

    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='movie_persons')
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='person_movies')
    role = models.CharField('Роль', max_length=20, choices=ROLE_CHOICES)
    character_name = models.CharField('Имя персонажа', max_length=255, blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Участие в фильме'
        verbose_name_plural = 'Участия в фильмах'
        ordering = ['order', 'id']
        unique_together = ['movie', 'person', 'role', 'character_name']

    def __str__(self):
        return f"{self.person} - {self.get_role_display()} в {self.movie}"


class FavoritePerson(models.Model):
    """Избранные персоны (актеры, режиссеры) пользователя"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorite_persons')
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField('Добавлено', auto_now_add=True)

    class Meta:
        verbose_name = 'Избранная персона'
        verbose_name_plural = 'Избранные персоны'
        unique_together = ['user', 'person']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} -> {self.person}"


class UserMovie(models.Model):
    """Пользовательский статус фильма: статус просмотра, избранное и оценка"""

    class WatchStatus(models.IntegerChoices):
        WATCHED = 1, 'Просмотрено'
        PLAN = 2, 'Буду смотреть'
        SKIP = 3, 'Не буду смотреть'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_movies')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='user_movies')
    watch_status = models.PositiveSmallIntegerField(
        'Статус просмотра',
        choices=WatchStatus,
        null=True,
        blank=True,
        db_index=True,
    )
    is_favorite = models.BooleanField('Избранное', default=False)
    rating = models.PositiveSmallIntegerField(
        'Оценка',
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        null=True,
        blank=True,
    )
    watched_at = models.DateField('Дата просмотра', null=True, blank=True, db_index=True)
    note = models.TextField('Заметка', blank=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Статус пользователя по фильму'
        verbose_name_plural = 'Статусы пользователей по фильмам'
        unique_together = ['user', 'movie']
        indexes = [
            models.Index(fields=['user', 'watch_status']),
            models.Index(fields=['user', 'is_favorite']),
        ]

    def __str__(self):
        return f"{self.user.username} -> {self.movie}"


class UserList(models.Model):
    """Пользовательские списки фильмов"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='movie_lists')
    name = models.CharField('Название', max_length=255)
    description = models.TextField('Описание', blank=True)
    is_public = models.BooleanField('Публичный', default=False)

    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлен', auto_now=True)

    class Meta:
        verbose_name = 'Список фильмов'
        verbose_name_plural = 'Списки фильмов'
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.name} ({self.user.username})"


class UserListMovie(models.Model):
    """Связь фильмов с пользовательскими списками"""
    user_list = models.ForeignKey(UserList, on_delete=models.CASCADE, related_name='list_movies')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='in_lists')
    added_at = models.DateTimeField('Добавлен', auto_now_add=True)
    # DEPRECATED note = models.TextField('Заметка', blank=True)

    class Meta:
        verbose_name = 'Фильм в списке'
        verbose_name_plural = 'Фильмы в списках'
        ordering = ['-added_at']
        unique_together = ['user_list', 'movie']

    def __str__(self):
        return f"{self.movie} в {self.user_list}"
