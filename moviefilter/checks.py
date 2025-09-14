from django.contrib.auth.models import User

from .models import MovieRSS
from .models import Kinorium
from .models import UserPreferences
from .classes import KinozalMovie
from .util import get_object_or_none
from .util import not_match_rating
from web_logger import log

from movie_filter_pro.settings import HIGH, LOW, DEFER, SKIP, WAIT_TRANS, TRANS_FOUND


def exist_in_kinozal(m: KinozalMovie) -> bool:
    """
    Возвращает True, если такой фильм уже присутствует в базе MovieRSS
    """
    movie_exist = MovieRSS.objects.filter(title=m.title, original_title=m.original_title, year=m.year)
    return bool(movie_exist)


def need_dubbed(m: KinozalMovie) -> bool:
    """
    Возвращает True, если фильм ждет дубляж.
    :param m:
    :return:
    """
    # todo move to model property
    movie_exist = MovieRSS.objects.filter(title=m.title, original_title=m.original_title, year=m.year)
    return bool(movie_exist and movie_exist.first().priority == WAIT_TRANS)


def exist_in_kinorium(m: KinozalMovie) -> [bool, bool, str | None]:
    """

    Выполняет частичные проверки.
    Первый возвращаемый аргумент - True, если такой фильм уже присутствует  в базе Kinorium.
    Второй возвращаемый аргумент показывает, было ли совпадение полное (True) или частичное (False)
    Если было совпадение, - третий аргумент это статус фильма в Кинориум - Просмотрен, Буду смотреть etc.
    """

    """
    У нас есть нестыковка в типах данных.
    В кинориум год - это всегда int.
    В кинозале год может быть периодом - 2008-2013.
    Поэтому если год - это период, то берем первые 4 цифры как для сравения.
    """
    NOT_FOUND = False
    MATCH = True
    FULL = True
    PARTIAL = False

    year = m.year if m.year.isdigit() else m.year[:4]

    exist = Kinorium.objects.filter(title=m.title, original_title=m.original_title, year=year)
    if exist:
        return MATCH, FULL, exist.first().get_status_display()

    exist = Kinorium.objects.filter(title=m.title, original_title=m.original_title)
    if exist:
        log(f' ┣━ KINORIUM PARTIAL MATCH [title+original]: {m.title} + {m.original_title}')
        return MATCH, PARTIAL, exist.first().get_status_display()

    if m.title:
        exist = Kinorium.objects.filter(title=m.title, year=year)
        if exist:
            log(f' ┣━ KINORIUM PARTIAL MATCH [title+year]: {m.title} + {year}')
            return MATCH, PARTIAL, exist.first().get_status_display()

    if m.original_title:
        exist = Kinorium.objects.filter(original_title=m.original_title, year=year)
        if exist:
            log(f' ┣━ KINORIUM PARTIAL MATCH [original+year]: {m.original_title} + {year}')
            return MATCH, PARTIAL, exist.first().get_status_display()

    """
    answer = True if exist else False  --> Возможно, заменить на bool(exist)
    
    После тестирование переделать так:
    
    partial1 = get_object_or_none(KinoriumMovie, title=m.title, original_title=m.original_title)
    partial2 = get_object_or_none(KinoriumMovie, title=m.title, year=m.year)
    partial3 = get_object_or_none(KinoriumMovie, original_title=m.original_title, year=m.year)
    answer = True if [partial1 + partial2 + partial3] else False
    
    Обычно quryset объеденяются так: q1.union(q2)
    Но будут проблемы, наверное, если вместо quryset будет None 
    """
    return NOT_FOUND, False, None


def check_users_filters(user: User, m: KinozalMovie, priority: int) -> bool:
    """
    Возвращает True, если m удовлетворяет всем фильтрам.
    """

    def prio(s: bool) -> str:
        return 'Low priority' if s else 'High priority'

    prefs = UserPreferences.get()
    if priority is LOW:
        stop_countries, stop_genres, max_year, min_rating = prefs.get_low_priority_preferences()
    elif priority is HIGH:
        stop_countries, stop_genres, max_year, min_rating = prefs.get_normal_preferences()


    ### 1 Countries
    country_intersection = set(m.countries.split(', ')) & set(stop_countries)
    # country_passes = not bool(country_intersection)
    if bool(country_intersection):
        if priority == LOW:
            log(f' ┣━ MARK LOW: [country] {country_intersection}')
        else:
            log(f' ┣━ SKIP: [country] {country_intersection}')
        return False

    ### 2 Genres
    genre_intersection = set(m.genres) & set(stop_genres)
    if bool(genre_intersection):
        if priority is LOW:
            log(f' ┣━ MARK LOW: [genres] {genre_intersection}')
        else:
            log(f' ┣━ SKIP: [genres] {genre_intersection}')
        return False

    ### 3 Max year
    # year can be dipason at website (as 2008-2012). If so, check last year (i.e 2012)
    # Если что-то пошло не так с преобразованием строки, считаем, что фильм прошел эту проверку
    try:
        if len(m.year) == 9:
            year = int(m.year[5:])
        else:
            year = int(m.year)
        if year < max_year:
            if priority is LOW:
                log(f' ┣━ MARK LOW: [year] {year}')
            else:
                log(f' ┣━ SKIP: [year] {year}')
            return False
    except:
        print('ERROR in checks.py -> checking_all_filters -> year converting')

    ### 4 Min rating
    if not_match_rating(m.kinopoisk_rating, min_rating) and not_match_rating(m.imdb_rating, min_rating):
        if priority is LOW:
            log(f' ┣━ MARK LOW: [rating] {m.kinopoisk_rating}/{m.imdb_rating}')
        else:
            log(f' ┣━ SKIP: [rating] {m.kinopoisk_rating}/{m.imdb_rating}')
        return False

    return True
