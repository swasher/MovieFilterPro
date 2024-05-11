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
    priority: bool = None
    kinorium_partial_match: bool = None


@dataclass
class KinoriumMovieDataClass:
    title: str = None
    original_title: str = None
    year: str = None
    status: int = None


@dataclass
class KinozalSearch:
    id: int = None
    header: str = None
    size: str = None
    seed: int = None
    peer: int = None
    created: str = None
    link: str = None
    is_4k: bool = None


class LinkConstructor:
    """
    https: // kinozal.tv / browse.php?c = 1002 & v = 3 & page = 74

    Parameters:
    c = 1001 - Все сериалы
    c = 1002 - Все фильмы
    c = 1003 - Все мультфильмы

    v = 3 - Рипы HD(1080 и 720)
    v = 7 - 4K

    page - номер страницы

    s - search by name

    d - year
    """

    browse = 'https://kinozal.tv/browse.php?'
    details = 'https://kinozal.tv/details.php?'

    def __init__(self, c=1002, v=3, page=0, d=None, s=None, id: int = None):
        self.c = c
        self.v = v
        self.page = page if page else 0
        self.id = id
        self.d = d
        self.s = s

    @staticmethod
    def link(root, payload):
        params = urlencode(payload, quote_via=quote_plus)
        # quote_plus - заменяет пробелы знаками +
        link = f"{root}{params}"
        return link

    def url(self):
        # линк на список фильмов
        payload = {'c': self.c, 'v': self.v, 'page': self.page}
        return self.link(self.browse, payload)

    def search_url(self):
        # линк на поиск фильмов
        payload = {'s': self.s, 'd': self.d, 'v': self.v}
        return self.link(self.browse, payload)

    def detail_url(self):
        # линк на страницу фильма
        payload = {'id': self.id}
        return self.link(self.details, payload)

    def prev_page(self):
        # первая страница на moviefilter'е имеет номер 0
        if self.page > 0:
            self.page -= 1
            return self.url()
        else:
            raise Exception("Can't get previous page")

    def next_page(self):
        self.page += 1
