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


def exist_in_kinorium(m: KinozalMovie) -> [bool, bool, str | None]:
    """

    Выполняет частичные проверки.
    Первый возвращаемый аргумент - True, если такой фильм уже присутствует  в базе Kinorium.
    Второй возвращаемый аргумент показывает, было ли совпадение полное (True) или частичное (False)
    Третий возвращаемый аргумент показывает, какой статус у фильма в базе Кинориум - Просмотрен, Буду смотреть etc.
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

    exist = get_object_or_none(KinoriumMovie, title=m.title, original_title=m.original_title, year=year)
    if exist:
        return MATCH, FULL, exist.get_status_display()

    exist = get_object_or_none(KinoriumMovie, title=m.title, original_title=m.original_title)
    if exist:
        print(f'  └─ DEBUG: partial match title+original: {m.title}+{m.original_title}')
        return MATCH, PARTIAL, exist.get_status_display()

    if m.title:
        exist = get_object_or_none(KinoriumMovie, title=m.title, year=year)
        if exist:
            print(f'   DEBUG: partial match title+year: {m.title}+{year}')
            return MATCH, PARTIAL, exist.get_status_display()

    if m.original_title:
        exist = get_object_or_none(KinoriumMovie, original_title=m.original_title, year=year)
        if exist:
            print(f'   DEBUG: partial match original+year: {m.original_title}+{year}')
            return MATCH, PARTIAL, exist.get_status_display()

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


def checking_all_filters(user: User, m: KinozalMovie, low_priority: bool) -> bool:
    """
    Возвращает True, если m удовлетворяет всем фильтрам.
    """

    def prio(s: bool) -> str:
        return 'Low priority' if s else 'High priority'

    prefs = UserPreferences.objects.get(user=user)
    if low_priority:
        stop_countries, stop_genres, max_year, min_rating = prefs.get_low_priority_preferences()
    else:
        stop_countries, stop_genres, max_year, min_rating = prefs.get_normal_preferences()


    ### 1 Countries
    country_passes = not bool(set(m.countries) & set(stop_countries))
    if not country_passes:
        print(f'└─ NOT MATCH in [{prio(low_priority)}]: [country]')
        return False

    ### 2 Genres
    genre_passes = not bool(set(m.genres) & set(stop_genres))
    if not country_passes:
        print(f'└─ NOT MATCH in [{prio(low_priority)}]: [genres]')
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
            print(f'└─ NOT MATCH in [{prio(low_priority)}]: [year]')
            return False
    except:
        print('ERROR in checks.py -> checking_all_filters -> year converting')


    ### 4 Min rating
    if m.kinopoisk_rating < min_rating and m.imdb_rating < min_rating:
        print(f'└─ NOT MATCH in [{prio(low_priority)}]: [rating]')
        return False

    return True
