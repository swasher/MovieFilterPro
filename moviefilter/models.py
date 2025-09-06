from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User

from movie_filter_pro.settings import HIGH, LOW, DEFER, SKIP, WAIT_TRANS, TRANS_FOUND

"""
Логика такая:
- парсер парсит moviefilter, находит фильм
- проверяет, есть ли фильм в базе
- добавляет этот фильм в базу при необходимости со статусом "НОВЫЙ"
- смотрит в эксель (или куда-то) от kinorium, и если там есть такой фильм, то соотв. меняет его статус.
"""


class Genre(models.Model):
    name = models.CharField(max_length=30)


class MovieRSS(models.Model):
    """
    Это фильмы с кинозала, которые ждут реакции юзера.
    Если пользователь нажал Ignore на фильме, он остается в базе с меткой Ignore. В дальнейшем, при сканированнии,
    сканер знает, что такие фильмы показывать пользователю не нужно.
    """

    PRIORITY = (
        (LOW, 'Низкий'),
        (HIGH, 'Обычный'),
        (DEFER, 'Отложено'),
        (SKIP, 'Отказ'),
        (WAIT_TRANS, 'Жду дубляж'),
        (TRANS_FOUND, 'Найден дубляж или ПМ'),
    )

    class Meta:
        ordering = ['date_added']

    # Похоже, что этот флаг не используется нигде
    # POSSIBLE DEPRECATED
    ignored_deprecated = models.BooleanField(default=False, help_text='Пользователь не хочет, чтобы этот фильм снова появился в ленте')

    low_priority_deprecated = models.BooleanField(default=False)
    priority = models.PositiveSmallIntegerField(choices=PRIORITY, verbose_name='Priority')
    kinozal_id = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=70)
    original_title = models.CharField(max_length=70)
    year = models.CharField(max_length=9, help_text='Год может быть представлен как диапазон: 1982-1994')
    date_added = models.DateField()
    dubbed = models.BooleanField(blank=True, null=True, help_text='Раздача имеет дубляж или ПМ. Нужно для передачи этой информации из сканера в чекер.')

    imdb_id = models.CharField(max_length=15, blank=True, null=True)
    imdb_rating = models.FloatField(blank=True, null=True)

    kinopoisk_id = models.PositiveSmallIntegerField(blank=True, null=True)
    kinopoisk_rating = models.FloatField(blank=True, null=True)

    genres = models.CharField(max_length=300)
    countries = models.CharField(max_length=300)

    director = models.CharField(max_length=300)
    actors = models.CharField(max_length=300)
    plot = models.CharField(max_length=1000)
    translate = models.CharField(max_length=300, blank=True, null=True)
    poster = models.CharField(max_length=100)

    kinorium_id = models.PositiveSmallIntegerField(blank=True, null=True, help_text='На данный момент не используется, потому что мы не можем получить ID из Кинориума')
    kinorium_partial_match = models.BooleanField(default=False, blank=True, null=True)

    @property
    def genres_as_list(self):
        return self.genres.split(', ')

    @property
    def countries_as_list(self):
        return self.countries.split(', ')

    @property
    def actors_as_list(self):
        return self.actors.split(', ')

    @property
    def director_as_list(self):
        return self.director.split(', ')

    def __str__(self):
        name = self.original_title if self.original_title else self.title
        return f"{name} - {self.year}"


class Kinorium(models.Model):
    """
    Эта таблица не имеет внешнего ключа к Moveies. Это просто копия CSV из Кинориума для более быстрого поиска(можно
    было бы просто по CSV искать)

    Поля kinozal_title и kinozal_original_title и kinozal_year нужны для того, чтобы в случае, если данные Кинозала
    не совпадают с данными Кинориума, пользователь мог нажать 'Fix it', и в базе будет записаны актуальные данные
    Кинозала. По ним в след раз и будет происходить поиск.

    Каждый раз, когда пользователь обновляет базу, она не перезаписывается, а только обновляются статусы.

    Если в таблице отсутствует original_title, то оригинальное название было на русском (возможно есть и другие причины)

    Чтобы проанализировать данные kinorium'а, нам нужно два списка - "Списки фильмов" и "Оценки и просмотры".
    В первом будут фильмы, которые "Буду смотреть" и "Не буду смотреть". У просмотренных фильмов нет назначенного
    списка, поэтому они вообще отсутствуют в этой таблице. Их мы извлекаем из "Оценки и просмотры".

    Если фильм присутствует в списке "Оценки и просмотры", значит он просмотрен. Он может как иметь мой рейтинг,
    так и быть без рейтинга.
    """

    UNKNOWN = 0
    WATCHED = 1
    WILL_WATCH = 2
    DECLINED = 3

    STATUS = (
        (UNKNOWN, 'Новый'),
        (WATCHED, 'Просмотрен'),
        (WILL_WATCH, 'Буду смотреть'),  # значит, уже скачан
        (DECLINED, 'Не буду смотреть'),
    )
    # ID фильма из Кинориума мы не можем получить
    title = models.CharField(max_length=50)
    original_title = models.CharField(max_length=50, blank=True)
    year = models.PositiveSmallIntegerField()

    status = models.PositiveSmallIntegerField(choices=STATUS, verbose_name='Статус', default=UNKNOWN)

    def __str__(self):
        return f'{self.title} - {self.year}'


class UserPreferences(models.Model):
    """
    Global Settings.
    Внимание! Я выпилил мультипользовательскую функциональность.
    Теперь настройки как бы едины для всех пользователей.
    Такой подход упрощает доступ к настройкам в разных частях приложения - им не требуется аутентифицированный юзер.
    Если понадобиться вернуться к поддерже мультипользователей - нужно передавать user по всей цепочке, особенно в parsing логику,
    и там брать настройки per user.

    Добавил удобный метод get(): теперь пользоваться настройками можно так:

        from moviefilter.models import UserPreferences

        preferences = UserPreferences.get()
        cookie_pass = preferences.cookie_pass
    """
    user = models.OneToOneField(User, unique=True, on_delete=models.CASCADE, related_name='preferences')
    last_scan = models.DateField(blank=True, null=True, default=timezone.now)
    scan_from_page = models.PositiveSmallIntegerField(blank=True, null=True, default=0, help_text='Если длительный скан оборвался, можно его продолжить с этой страницы до последней.')

    countries = models.CharField(max_length=300, default='СССР, Россия, Индия')
    genres = models.CharField(max_length=300, default='Мюзикл')
    max_year = models.PositiveSmallIntegerField(default=1990)
    min_rating = models.FloatField(default=3.0)

    low_countries = models.CharField(max_length=300, default='Таиланд, Япония, Южная Корея, Китай')
    low_genres = models.CharField(max_length=300, default='Ужасы')
    low_max_year = models.PositiveSmallIntegerField(default=2000)
    low_min_rating = models.FloatField(default=5.0)

    plex_address = models.CharField(max_length=100, blank=True, null=True)
    plex_token = models.CharField(max_length=25, blank=True, null=True)

    cookie_pass = models.CharField(max_length=25, blank=True, null=True)
    cookie_uid = models.CharField(max_length=25, blank=True, null=True)
    kinozal_domain = models.CharField(max_length=50, blank=True, null=True)
    torrents_hotfolder = models.CharField(max_length=70, blank=True, null=True)

    ignore_title = models.CharField(max_length=500, default='')

    def save(self, *args, **kwargs):
        self.pk = 1  # всегда используем один и тот же primary key, потому что это БД-синглтон с одной записью
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def get_normal_preferences(self) -> tuple[list[str], list[str], int, float]:
        countries = self.countries.split(', ') if self.countries else []
        genres = self.genres.split(', ') if self.genres else []
        return countries, genres, self.max_year, self.min_rating

    def get_low_priority_preferences(self) -> tuple[list[str], list[str], int, float]:
        countries = self.low_countries.split(', ') if self.countries else []
        genres = self.low_genres.split(', ') if self.genres else []
        return countries, genres, self.low_max_year, self.low_min_rating

    class Meta:
        verbose_name = "User Preferences"
        verbose_name_plural = "User Preferences"


class Country(models.Model):
    """
    Нужно потому, что в Kinozale в одном поле и страны и студии. С помощью списка известных стран будем отделять
     одни от других.
    """
    name = models.CharField(max_length=60, unique=True)

    def __str__(self):
        return self.name
