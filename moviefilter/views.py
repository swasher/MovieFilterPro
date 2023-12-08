
import dataclasses

from datetime import date, datetime

from django.db.models import Q
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.template.defaultfilters import safe
from django import forms
from django.contrib.auth.models import User
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from plexapi.server import PlexServer

from .models import MovieRSS, KinoriumMovie, UserPreferences
from .classes import LinkConstructor
from .parse import parse_browse
from .checks import exist_in_kinorium, exist_in_kinozal, checking_all_filters
from .parse import get_details
from .models import MovieRSS
from .forms import PreferencesForm
from .parse_csv import parse_file_movie_list, parse_file_votes



@login_required()
def movies(request):
    movies = MovieRSS.objects.filter(low_priority=False, ignored=False)
    paginator = Paginator(movies, 5)
    page_number = request.GET.get("page")
    movies_page = paginator.get_page(page_number)

    last_scan = UserPreferences.objects.get(user=request.user).last_scan
    return render(request, template_name='movies.html', context={'movies': movies_page, 'last_scan': last_scan})


def movies_low(request):
    movies = MovieRSS.objects.filter(low_priority=True, ignored=False)
    last_scan = UserPreferences.objects.get(user=request.user).last_scan
    return render(request, template_name='movies.html', context={'movies': movies, 'last_scan': last_scan})


# def from_line(line: str) -> list[str]:
#     return next(csv.reader([line]))


def parse_kinorium_csv(request):

    if request.method == 'POST':

        if 'file_votes' in request.FILES and 'file_movie_list' in request.FILES:

            objs = KinoriumMovie.objects.all()
            objs.delete()

            print('\nСканируем "Списки фильмов"')
            dict_obj_with_movies = parse_file_movie_list(request.FILES['file_movie_list'])
            django_list = [KinoriumMovie(**dataclasses.asdict(vals)) for vals in dict_obj_with_movies]
            f = KinoriumMovie.objects.bulk_create(django_list)
            print(f'-- Movies added: {len(f)}')

            print('\nСканируем "Отметки"')
            dict_obj_with_movies = parse_file_votes(request.FILES['file_votes'])
            django_list = [KinoriumMovie(**dataclasses.asdict(vals)) for vals in dict_obj_with_movies]
            f = KinoriumMovie.objects.bulk_create(django_list)
            print(f'-- Movies added: {len(f)}')

            return HttpResponse(safe("<b style='color:green'>Update success!</b>"))

        else:
            html = "<b style='color:red'>Need both files!</b>"
            return HttpResponse(safe(html))

    return render(request, 'upload_csv.html')


@login_required()
def reset_rss(requst):
    # htmx function
    if requst.method == 'DELETE':
        rss = MovieRSS.objects.all()
        rss.delete()
        context = {'answer': 'MovieRSS table is cleaned.'}
        messages.success(requst, 'Success!')
        return HttpResponse(status=200)


# DEPRECATED
# @login_required()
# def scan_page(request):
#     last_scan = UserPreferences.objects.get(user=request.user).last_scan
#     return render(request, 'deprecated_scan.html', {'last_scan': last_scan})


@login_required()
def scan(request):
    last_scan = UserPreferences.objects.get(user=request.user).last_scan
    context = {'last_scan': last_scan}

    if request.method == 'GET':

        site = LinkConstructor()
        movies = parse_browse(site, last_scan)

        for m in movies:
            """
            LOGIC:
            - если есть в базе moviefilter - пропускаем (предложение о скачивании показывается пользователю один раз)
                ◦ так же этот фильм может быть уже в базе как Игнорируемый - в коде никаких дополнительных действий не требуется, просто не добавляем.
            - если есть в базе kinorium - пропускаем (любой статус в кинориуме, - просмотрено, буду смотреть, не буду смотреть)
                ◦ проверяем также частичное совпадение, и тогда записываем в базу, а пользователю предлагаем установить связь через поля кинориума
            - если фильм прошел проверки по базам, тогда вытягиваем для него данные со страницы
            - проверяем через пользовательские фильтры
            - и вот теперь только заносим в базу 
            """
            print(f'START: {m.title} - {m.original_title} - {m.year}')

            if exist_in_kinozal(m):
                print(f' ┣━ SKIP [moviefilter]')
                continue

            exist, match_full, status = exist_in_kinorium(m)
            if exist and match_full:
                print(f' ┣━ SKIP [{status}]')
                continue
            elif exist and not match_full:
                print(f' ┣━ ADD AS PARTIAL [{status}]')
                m.kinorium_partial_match = True

            m, sec = get_details(m)
            print(f' ┣━ GET DETAILS: {sec:.1f}s')

            # Этот фильтр выкидвает все, что через него не прошло
            if checking_all_filters(request.user, m, low_priority=False):
                m.low_priority = False

                # Из оставшихся, некоторым назначаем низкий приоритет
                # тут логика такая - если фильм НЕ прошел проверку - то он подпадет как Low priority
                if not checking_all_filters(request.user, m, low_priority=True):
                    m.low_priority = True

            if m.low_priority is not None:
                print(f' ┣━ ADD TO DB [prio={"low" if m.low_priority else "high"}] [partial={"YES" if m.kinorium_partial_match else "NO"}]')
                MovieRSS.objects.get_or_create(title=m.title, original_title=m.original_title, year=m.year,
                                               defaults=dataclasses.asdict(m))

        UserPreferences.objects.filter(user=request.user).update(last_scan=datetime.now().date())

        movies = MovieRSS.objects.filter(low_priority=False, ignored=False)
        paginator = Paginator(movies, 5)
        page_number = request.GET.get("page")
        movies_page = paginator.get_page(page_number)
        context['movies'] = movies_page
        return render(request, 'partials/scan-table.html', context)

def user_preferences_update(request):
    user = User.objects.get(pk=request.user.pk)
    pref, _ = UserPreferences.objects.get_or_create(user=user)
    form = PreferencesForm(request.POST or None, instance=pref)

    if request.method == 'POST':
        if form.is_valid():
            # pref = UserPreferences.objects.get_or_create(user=request.user)
            pref.last_scan = form.cleaned_data['last_scan']
            pref.countries = form.cleaned_data['countries']
            pref.genres = form.cleaned_data['genres']
            pref.max_year = int(form.cleaned_data['max_year'])
            pref.min_rating = float(form.cleaned_data['min_rating'])

            pref.low_countries = form.cleaned_data['low_countries']
            pref.low_genres = form.cleaned_data['low_genres']
            pref.low_max_year = int(form.cleaned_data['low_max_year'])
            pref.low_min_rating = float(form.cleaned_data['low_min_rating'])
            pref.save()
            return redirect(reverse('moviefilter:user_preferences'))
    return render(request, 'preferences_update_form.html', {'form': form})


def plex(request):
    baseurl = 'http://127.0.0.1:32400'
    token = '4xNQeFuz8ty2A4omgxXB'
    try:
        plex = PlexServer(baseurl, token)
    except:
        return render(request, 'plex.html', {'error': 'No Plex connection'})

    m = plex.library.section('Фильмы')
    movies = m.search()
    for mov in movies:
        print(mov)
    return render(request, 'plex.html', {'movies': movies})


def kinorium(request):
    if request.htmx and request.method == 'GET':
        query_text = request.GET.get('filter')
        movies = KinoriumMovie.objects.filter(
            Q(title__contains=query_text) |
            Q(original_title__contains=query_text) |
            Q(year__contains=query_text)
        )
        return render(request, 'partials/kinorium-table.html', {'movies': movies})

    movies = KinoriumMovie.objects.all()
    return render(request, 'kinorium.html', {'movies': movies})


def ignore_movie(request, pk):
    # htmx
    if request.method == 'DELETE':
        try:
            MovieRSS.objects.filter(pk=pk).update(ignored=True)
            messages.success(request, f"'{MovieRSS.objects.get(pk=pk).title}' remove successfully")
            return HttpResponse(status=200)
        except:
            messages.error(request, f"Error with removing Movie pk={pk}")
            return HttpResponse(status=500)
