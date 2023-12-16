from urllib.parse import urlencode, quote_plus
from collections import namedtuple
from dataclasses import dataclass
import datetime
from typing import Any, List


@dataclass
class KinozalMovie:
    kinozal_id: int = None
    title: str = None
    original_title: str = None
    year: str = None
    date_added: datetime.date = None
    imdb_id: str = None
    imdb_rating: float = None
    kinopoisk_id: int = None
    kinopoisk_rating: float = None
    genres: str = None
    countries: str = None
    director: str = None
    actors: List[str] = None
    plot: str = None
    translate: str = None
    poster: str = None
    low_priority: bool = None
    kinorium_partial_match: bool = None


@dataclass
class KinoriumMovieDataClass:
    title: str = None
    original_title: str = None
    year: str = None
    status: int = None


class LinkConstructor:
    """
    https: // moviefilter.tv / browse.php?c = 1002 & v = 3 & page = 74

    Parameters:
    c = 1001 - Все сериалы
    c = 1002 - Все фильмы
    c = 1003 - Все мультфильмы

    v = 3 - Рипы HD(1080 и 720)
    v = 7 - 4K

    page - номер страницы

    s - search by name
    """

    head = 'https://kinozal.tv/browse.php?'

    def __init__(self, c=1002, v=3, page=0, id: int = None):
        self.c = c
        self.v = v
        self.page = page if page else 0
        self.id = id

    def url(self):
        # линк на список фильмов
        payload = {'c': self.c, 'v': self.v, 'page': self.page}
        params = urlencode(payload, quote_via=quote_plus)
        # quote_plus - заменяет пробелы знаками +
        link = f"https://kinozal.tv/browse.php?{params}"
        return link

    def detail_url(self):
        # линк на страницу фильма
        payload = {'id': self.id}
        params = urlencode(payload, quote_via=quote_plus)
        # quote_plus - заменяет пробелы знаками +
        link = f"https://kinozal.tv/details.php?{params}"
        return link

    def prev_page(self):
        # первая страница на moviefilter'е имеет номер 0
        if self.page > 0:
            self.page -= 1
            return self.url()
        else:
            raise Exception("Can't get previous page")

    def next_page(self):
        self.page += 1
