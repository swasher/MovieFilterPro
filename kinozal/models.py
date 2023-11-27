from django.db import models
from urllib.parse import urlencode, quote_plus
from datetime import datetime, timedelta
from django.contrib.auth.models import User


"""
Логика такая:
- парсер парсит kinozal, находит фильм
- проверяет, есть ли фильм в базе
- добавляет этот фильм в базу при необходимости со статусом "НОВЫЙ"
- смотрит в эксель (или куда-то) от kinorium, и если там есть такой фильм, то соотв. меняет его статус.
"""


class Genre(models.Model):
    name = models.CharField(max_length=30)


class Movie(models.Model):

    UNKNOWN = 0
    WATCHED = 1
    TO_WATCH = 2
    DECLINED = 3

    STATUS = (
        (UNKNOWN, 'Новый'),
        (WATCHED, 'Просмотрен'),
        (TO_WATCH, 'Буду смотреть'),  # значит, уже скачан
        (DECLINED, 'Не буду смотреть'),
    )

    ru_name = models.CharField(max_length=70)
    en_name = models.CharField(max_length=70)
    year = models.PositiveSmallIntegerField()
    status = models.PositiveSmallIntegerField(choices=STATUS, verbose_name='Статус', default=UNKNOWN)

    imdb_id = models.PositiveSmallIntegerField()
    kinopoisk_id = models.PositiveSmallIntegerField()
    kinorium_id = models.PositiveSmallIntegerField()

    genres = models.ManyToManyField(Genre, related_name='movies')

    def search_link(self):
        # for "Мизантроп / Misanthrope" and 2023
        #link = "https://kinozal.tv/browse.php?s=%CC%E8%E7%E0%ED%F2%F0%EE%EF+%2F+Misanthrope&g=0&c=1002&v=3&d=2023&w=0&t=0&f=0"

        # c = 1002 for movies, 1001 for serials
        payload = {'s': f'{self.ru_name} / {self.en_name}', 'd': f'{self.year}', 'c': '1002'}
        params = urlencode(payload, quote_via=quote_plus)
        # quote_plus - заменяет пробелы знаками +
        # 'password=xyz&username=administrator'

        link = f"https://kinozal.tv/browse.php?{params}"
        return link


class KinoriumMovie(models.Model):
    """
    Эта таблица не имеет внешнего ключа к Moveies. Это просто копия CSV для более быстрого поиска.
    Каждый раз, когда CSV обновляется, данные в этой таблице полностью удаляются и заменяются новыми.

    Если в таблице отсутствует original_title, то оригинальное название было на русском (возможно есть и другие причины)

    Чтобы проанализировать данные kinorium'а, нам нужно два списка - "Списки фильмов" и "Оценки и просмотры".
    В первом будут фильмы, которые "Буду смотреть" и "Не буду смотреть". У просмотренных фильмов нет назначенного
    списка, поэтому они вообще отсутствуют в этой таблице. Их мы извлекаем из "Оценки и просмотры".

    Если фильм присутствует в списке "Оценки и просмотры", значит он просмотрен. Он может как иметь мой рейтинг,
    так и быть без рейтинга.
    """

    UNKNOWN = 0
    WATCHED = 1
    TO_WATCH = 2
    DECLINED = 3

    STATUS = (
        (UNKNOWN, 'Новый'),
        (WATCHED, 'Просмотрен'),
        (TO_WATCH, 'Буду смотреть'),  # значит, уже скачан
        (DECLINED, 'Не буду смотреть'),
    )

    title = models.CharField(max_length=50)
    original_title = models.CharField(max_length=50)
    year = models.PositiveSmallIntegerField()
    status = models.PositiveSmallIntegerField(choices=STATUS, verbose_name='Статус', default=UNKNOWN)


class UserPreferences(models.Model):
    """
    Settings per user. Do not show in admin.
    """
    user = models.OneToOneField(User, unique=True, on_delete=models.CASCADE)
    last_scan = models.DateField(default=datetime.now() - timedelta(days=180))
