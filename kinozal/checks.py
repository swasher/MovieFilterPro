from django.contrib.auth.models import User

from .models import MovieRSS
from .models import KinoriumMovie
from .models import UserPreferences
from .classes import KinozalMovie
from .util import get_object_or_none


def exist_in_kinozal(m: KinozalMovie) -> bool:
    """
    Возвращает True, если такой фильм уже присутствует в базе MovieRSS
    """
    exist = get_object_or_none(MovieRSS, title=m.title, original_title=m.original_title, year=m.year)
    answer = True if exist else False
    return answer


def exist_in_kinorium(m: KinozalMovie) -> [bool, bool]:
    """
    Возвращает True, если такой фильм уже присутствует  в базе MovieRSS.
    Выполняет частичные проверки.
    Второй возвращаемый аргумент показывает, было ли совпадение полное (True) или частичное (False)
    """

    """
    У нас есть нестыковка в типах данных.
    В кинориум год - это всегда int.
    В кинозале год может быть периодом - 2008-2013.
    Поэтому если год - это период, то берем первые 4 цифры как для сравения.
    """

    year = m.year if m.year.isdigit() else m.year[:4]


    exist = get_object_or_none(KinoriumMovie, title=m.title, original_title=m.original_title, year=year)
    answer = True if exist else False
    if answer:
        return True #, True

    exist = get_object_or_none(KinoriumMovie, title=m.title, original_title=m.original_title)
    answer = True if exist else False
    if answer:
        return True #, False

    exist = get_object_or_none(KinoriumMovie, title=m.title, year=year)
    answer = True if exist else False
    if answer:
        return True #, False

    exist = get_object_or_none(KinoriumMovie, original_title=m.original_title, year=year)
    answer = True if exist else False
    if answer:
        return True #, False

    """
    После тестирование переделать так:
    
    partial1 = get_object_or_none(KinoriumMovie, title=m.title, original_title=m.original_title)
    partial2 = get_object_or_none(KinoriumMovie, title=m.title, year=m.year)
    partial3 = get_object_or_none(KinoriumMovie, original_title=m.original_title, year=m.year)
    answer = True if [partial1 + partial2 + partial3] else False
    
    Обычно quryset объеденяются так: q1.union(q2)
    Но будут проблемы, наверное, если вместо quryset будет None 
    """

    return False #, True


def pass_all_filters(user: User, m: KinozalMovie) -> bool:
    """
    Возвращает True, если m удовлетворяет всем фильтрам.
    """

    ### 1 Countries
    stop_countries = UserPreferences.objects.get(user=user).countries.split(', ')
    country_passes = not bool(set(m.countries) & set(stop_countries))
    if not country_passes:
        print(f'STOP country detected in {m.title} - {m.year}')
        return False

    ### 2 Genres
    stop_genres = UserPreferences.objects.get(user=user).countries.split(', ')
    genre_passes = not bool(set(m.genres) & set(stop_genres))
    if not country_passes:
        print(f'STOP country detected in {m.title} - {m.year}')
        return False

    ### 3 Max year


    ### 4 Min rating

    return True
