"""
Сканирует определенную страницу (переменная page).
Модифицированная функция из основного приложения для дебага.
"""
import os
import sys
from django.core.wsgi import get_wsgi_application

# Добавляем корень проекта в sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'movie_filter_pro.settings')
application = get_wsgi_application()


from django.shortcuts import get_object_or_404

# from movie_filter_pro import wsgi
from moviefilter.classes import LinkConstructor
from datetime import date
import dataclasses
from django.contrib.auth.models import User
from moviefilter.models import MovieRSS, UserPreferences
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

    user = User.objects.filter(email='mr.swasher@gmail.com').first()
    pref = get_object_or_404(UserPreferences, user=user)
    kinozal_domain = pref.kinozal_domain
    if not kinozal_domain or not kinozal_domain.strip():
        raise Exception('Нужно ввести домен kinozal в настройках')

    page = LinkConstructor(page=page)

    modified_kinozal_scan(page, user)
