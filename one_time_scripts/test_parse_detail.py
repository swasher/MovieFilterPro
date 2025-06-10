"""
Сканирует определенную страницу (переменная page).
Модифицированная функция из основного приложения для дебага.
"""
from movie_filter_pro import wsgi
from moviefilter.classes import LinkConstructor
from datetime import date
import dataclasses
from django.contrib.auth.models import User
from moviefilter.models import MovieRSS
from moviefilter.parse import parse_page, movie_audit


def modified_kinozal_scan(site: LinkConstructor, user):
    scan_to_date = date(year=2000, month=1, day=1)

    # Получаем список всех фильмов со страницы. Если достигли нужной даты, то reach_last_day возврашается как True
    movies, reach_last_day = parse_page(site, scan_to_date)

    # Проверяем список по фильтрам, и получаем отфильтрованный и заполненный список, который можно уже заносить в базу
    movies = movie_audit(movies, user)

    # типа записываем фильмы в базу:
    for m in movies:
        print(m.title)



if __name__ == '__main__':
    page = 1

    page = LinkConstructor(page=page)
    user = User.objects.get(pk=1)

    modified_kinozal_scan(page, user)
