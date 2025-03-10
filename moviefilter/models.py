from urllib.parse import urlencode, quote_plus
from typing import List, Tuple
from datetime import datetime

from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

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

    @property
    def search_link(self):
        # for "Мизантроп / Misanthrope" and 2023
        # link = "https://kinozal.tv/browse.php?s=%CC%E8%E7%E0%ED%F2%F0%EE%EF+%2F+Misanthrope&g=0&c=1002&v=3&d=2023&w=0&t=0&f=0"

        # c = 1002 for movies, 1001 for serials
        # v = 3 for Рипы HD(1080|720)
        payload = {'s': f'{self.title} / {self.original_title}', 'd': f'{self.year}', 'c': '1002', 'v': 3}
        params = urlencode(payload, quote_via=quote_plus)
        # quote_plus - заменяет пробелы знаками +
        # 'password=xyz&username=administrator'

        link = f"https://kinozal.tv/browse.php?{params}"
        return link

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
    Settings per user.
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
    torrents_hotfolder = models.CharField(max_length=70, blank=True, null=True)

    ignore_title = models.CharField(max_length=500, default='')

    def get_normal_preferences(self) -> Tuple[List[str], List[str], int, float]:
        countries = self.countries.split(', ') if self.countries else []
        genres = self.genres.split(', ') if self.genres else []
        return countries, genres, self.max_year, self.min_rating

    def get_low_priority_preferences(self) -> Tuple[List[str], List[str], int, float]:
        countries = self.low_countries.split(', ') if self.countries else []
        genres = self.low_genres.split(', ') if self.genres else []
        return countries, genres, self.low_max_year, self.low_min_rating

"""
Когда создается юзер, для него сразу создается записть UserPreferences.
Мне удобнее здесь держать, а не в signals.py
Потому что это нужно 
"""
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserPreferences.objects.create(user=instance)

class Country(models.Model):
    """
    Нужно потому, что в Kinozale в одном поле и страны и студии. С помощью списка известных стран будем отделять одни о
    от других.
    """
    name = models.CharField(max_length=60, unique=True)

    def __str__(self):
        return self.name
