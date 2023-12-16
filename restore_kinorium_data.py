"""
После того, как я грохнул поля в MovieRSS kinorium_id и kinorium_partial_match,
написал скрипт, который еще раз отсканит весь кинозал и восстановит поля.

Фишка в том, что мы не будем делать заходить внутрь фильмов, только парсить список фильмов, для ускорения.
"""
from movie_filter_pro import wsgi
from moviefilter.classes import LinkConstructor
from datetime import date
import dataclasses
from django.contrib.auth.models import User
from moviefilter.models import MovieRSS
from moviefilter.parse import parse_page, movie_audit
from moviefilter.checks import exist_in_kinorium
from django.core.exceptions import ObjectDoesNotExist


def modified_kinozal_scan(site: LinkConstructor, user):
    # Fake date
    scan_to_date = date(year=2000, month=1, day=1)

    # Получаем список всех фильмов со страницы. Если достигли нужной даты, то reach_last_day возврашается как True
    movies, reach_last_day = parse_page(site, scan_to_date)

    # Проверяем список по фильтрам, и получаем отфильтрованный и заполненный список, который можно уже заносить в базу
    # movies = movie_audit(movies, user)

    # типа записываем фильмы в базу:
    for m in movies:
        exist, full_match, status = exist_in_kinorium(m)

        try:
            rss_m = MovieRSS.objects.get(title=m.title, original_title=m.original_title, year=m.year)
            found = 'FOUND'
        except MovieRSS.DoesNotExist:
            found = 'NOT_FOUND'

        print('{: <40}'.format(m.title[:40]), '\t', exist, full_match, status, found)





if __name__ == '__main__':
    page = 5

    page = LinkConstructor(page=page)
    user = User.objects.get(pk=1)

    modified_kinozal_scan(page, user)
