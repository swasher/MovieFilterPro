from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from slugify import slugify
from django.conf import settings
from core.models import Country


class Person(models.Model):
    """Модель для актеров, режиссеров и других людей"""
    GENDER_CHOICES = [
        ('M', 'Мужской'),
        ('F', 'Женский'),
    ]

    first_name = models.CharField('Имя', max_length=100)
    last_name = models.CharField('Фамилия', max_length=100)
    birth_date = models.DateField('Дата рождения', null=True, blank=True)
    death_date = models.DateField('Дата смерти', null=True, blank=True)
    gender = models.CharField('Пол', max_length=1, choices=GENDER_CHOICES, blank=True)
    # photo = models.ImageField('Фото', upload_to='persons/', null=True, blank=True)
    photo = models.CharField('Путь к фото', max_length=255, blank=True, null=True, help_text='Относительный путь к фото (например: /pynwU6PGLAdDE840rC9m6jEahWg.jpg)')
    biography = models.TextField('Биография', blank=True)
    country = models.CharField('Страна', max_length=100, blank=True)
    #country = models.ForeignKey(Country, on_delete=models.RESTRICT)

    class Meta:
        verbose_name = 'Персона'
        verbose_name_plural = 'Персоны'
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def photo_url(self):
        """Генерируем полный URL на лету"""
        if self.photo:
            # Базовый URL из настроек (например, для TMDB)
            base_url = settings.TMDB_IMAGE_BASE_URL  # 'https://image.tmdb.org/t/p/'
            size = settings.TMDB_IMAGE_SIZE  # 'w500', 'original', etc.
            return f"{base_url}{size}{self.photo}"
        return None

    def get_photo_url(self, size='w500'):
        """Метод для получения URL с конкретным размером"""
        if self.photo:
            base_url = settings.TMDB_IMAGE_BASE_URL
            return f"{base_url}{size}{self.photo}"
        return None


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
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# class Country(models.Model):
#     """Модель стран производства"""
#     name = models.CharField('Название', max_length=100, unique=True)
#     code = models.CharField('Код', max_length=2, unique=True, blank=True)
#
#     class Meta:
#         verbose_name = 'Страна'
#         verbose_name_plural = 'Страны'
#         ordering = ['name']
#
#     def __str__(self):
#         return self.name


class Movie(models.Model):
    """Основная модель фильма"""
    STATUS_CHOICES = [
        ('announced', 'Анонсирован'),
        ('production', 'В производстве'),
        ('post_production', 'Пост-продакшн'),
        ('released', 'Вышел'),
        ('cancelled', 'Отменен'),
    ]

    TYPE_CHOICES = [
        ('movie', 'Фильм'),
        ('series', 'Сериал'),
        ('cartoon', 'Мультфильм'),
        ('anime', 'Аниме'),
        ('show', 'Шоу'),
    ]

    title = models.CharField('Название', max_length=255)
    original_title = models.CharField('Оригинальное название', max_length=255, blank=True, null=True)
    slug = models.SlugField('URL', unique=True, blank=True)
    description = models.TextField('Описание', blank=True)

    year = models.PositiveIntegerField('Год выпуска', null=True, blank=True)
    is_ongoing = models.BooleanField('Выходит сейчас', default=False)
    year_end = models.PositiveIntegerField('Год окончания', null=True, blank=True)

    duration = models.PositiveIntegerField('Длительность (мин)', null=True, blank=True)
    release_date = models.DateField('Дата выхода', null=True, blank=True)

    movie_type = models.CharField('Тип', max_length=20, choices=TYPE_CHOICES, default='movie')
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default='released')

    # poster = models.ImageField('Постер', upload_to='posters/', null=True, blank=True)
    poster = models.CharField('Путь к фото', max_length=255, blank=True, null=True, help_text='Относительный путь к фото (например: /pynwU6PGLAdDE840rC9m6jEahWg.jpg)')
    trailer_url = models.URLField('Ссылка на трейлер', blank=True)

    genres = models.ManyToManyField(Genre, verbose_name='Жанры', related_name='movies')
    countries = models.ManyToManyField(Country, verbose_name='Страны', related_name='movies')

    age_rating = models.CharField('Возрастной рейтинг', max_length=10, blank=True)
    budget = models.DecimalField('Бюджет', max_digits=12, decimal_places=2, null=True, blank=True)
    box_office = models.DecimalField('Сборы', max_digits=12, decimal_places=2, null=True, blank=True)

    imdb_rating = models.DecimalField('Рейтинг IMDb', max_digits=3, decimal_places=1, null=True, blank=True)
    imdb_votes = models.PositiveIntegerField('Голосов IMDb', null=True, blank=True)

    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

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
        ratings = self.ratings.all()
        if ratings:
            return sum(r.rating for r in ratings) / len(ratings)
        return None

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
    release_date = models.DateField('Дата выхода', null=True, blank=True)
    poster = models.ImageField('Постер', upload_to='seasons/', null=True, blank=True)

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


class Review(models.Model):
    """Отзывы пользователей"""
    REVIEW_TYPE_CHOICES = [
        ('positive', 'Положительный'),
        ('negative', 'Отрицательный'),
        ('neutral', 'Нейтральный'),
    ]

    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    title = models.CharField('Заголовок', max_length=255)
    text = models.TextField('Текст отзыва')
    review_type = models.CharField('Тип', max_length=10, choices=REVIEW_TYPE_CHOICES)

    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлен', auto_now=True)

    likes = models.ManyToManyField(User, related_name='liked_reviews', blank=True)

    class Meta:
        verbose_name = 'Рецензия'
        verbose_name_plural = 'Рецензии'
        ordering = ['-created_at']
        unique_together = ['movie', 'user']

    def __str__(self):
        return f"Рецензия {self.user.username} на {self.movie}"

    def likes_count(self):
        return self.likes.count()


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


class Rating(models.Model):
    """Оценки фильмов пользователями"""
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='ratings')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ratings')
    rating = models.PositiveSmallIntegerField(
        'Оценка',
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    created_at = models.DateTimeField('Создана', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлена', auto_now=True)

    class Meta:
        verbose_name = 'Оценка'
        verbose_name_plural = 'Оценки'
        unique_together = ['movie', 'user']

    def __str__(self):
        return f"{self.user.username}: {self.rating}/10 для {self.movie}"


class UserList(models.Model):
    """Пользовательские списки фильмов"""
    LIST_TYPE_CHOICES = [
        ('watched', 'Просмотрено'),
        ('will_watch', 'Буду смотреть'),
        ('wont_watch', 'Не буду смотреть'),
        ('favorites', 'Избранное'),
        ('custom', 'Пользовательский'),
    ]

    SYSTEM_LIST_TYPES = ['watched', 'will_watch', 'wont_watch', 'favorites']

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='movie_lists')
    name = models.CharField('Название', max_length=255)
    description = models.TextField('Описание', blank=True)
    list_type = models.CharField('Тип списка', max_length=20, choices=LIST_TYPE_CHOICES)
    is_public = models.BooleanField('Публичный', default=False)
    is_system = models.BooleanField('Системный список', default=False)
    order = models.PositiveIntegerField('Порядок', default=0)

    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлен', auto_now=True)

    class Meta:
        verbose_name = 'Список фильмов'
        verbose_name_plural = 'Списки фильмов'
        ordering = ['order', '-updated_at']
        unique_together = [['user', 'list_type']]
        indexes = [
            models.Index(fields=['user', 'is_system']),
        ]

    def __str__(self):
        return f"{self.name} ({self.user.username})"

    def save(self, *args, **kwargs):
        # Системные списки нельзя изменить на обычные и наоборот
        if self.pk:
            old_instance = UserList.objects.get(pk=self.pk)
            if old_instance.is_system != self.is_system:
                raise ValueError("Нельзя изменить тип списка (системный/пользовательский)")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Извлекаем флаг принудительного удаления
        force = kwargs.pop('force', False)
        if self.is_system and not force:
            raise ValueError("Системные списки нельзя удалять")
        super().delete(*args, **kwargs)

    @classmethod
    def create_system_lists(cls, user):
        """Создает системные списки для нового пользователя"""
        system_lists = [
            {'list_type': 'watched', 'name': 'Просмотрено', 'order': 1},
            {'list_type': 'will_watch', 'name': 'Буду смотреть', 'order': 2},
            {'list_type': 'wont_watch', 'name': 'Не буду смотреть', 'order': 3},
            {'list_type': 'favorites', 'name': 'Избранное', 'order': 4},
        ]

        created_lists = []
        for list_data in system_lists:
            user_list, created = cls.objects.get_or_create(
                user=user,
                list_type=list_data['list_type'],
                defaults={
                    'name': list_data['name'],
                    'is_system': True,
                    'order': list_data['order'],
                }
            )
            created_lists.append(user_list)

        return created_lists

    @classmethod
    def delete_user_completely(cls, user):
        """
        Безопасное удаление пользователя и всех связанных с ним данных.
        Обходит защиту удаления системных списков.
        """
        # 1. Принудительно удаляем системные списки пользователя
        # Используем итерацию, чтобы вызвать метод delete() с флагом force
        for user_list in cls.objects.filter(user=user, is_system=True):
            user_list.delete(force=True)

        # 2. Удаляем пользователя
        # Все остальные данные (обычные списки, оценки, рецензии) удалятся каскадно
        user.delete()


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


class Comment(models.Model):
    """Комментарии к фильмам"""
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    text = models.TextField('Текст комментария')

    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлен', auto_now=True)

    likes = models.ManyToManyField(User, related_name='liked_comments', blank=True)

    class Meta:
        verbose_name = 'Комментарий'
        verbose_name_plural = 'Комментарии'
        ordering = ['-created_at']

    def __str__(self):
        return f"Комментарий {self.user.username} к {self.movie}"

    def likes_count(self):
        return self.likes.count()


class MovieNote(models.Model):
    """Личные заметки пользователя к фильмам (скрыты от других)"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='movie_notes')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='user_notes')
    text = models.TextField('Текст заметки')

    created_at = models.DateTimeField('Создана', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлена', auto_now=True)

    class Meta:
        verbose_name = 'Личная заметка'
        verbose_name_plural = 'Личные заметки'
        unique_together = ['user', 'movie']  # Одна заметка на один фильм от пользователя
        ordering = ['-updated_at']

    def __str__(self):
        return f"Заметка {self.user.username} к {self.movie}"
