import os
import time

import requests
from datetime import datetime
from pathlib import Path
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib import messages
from django.http import HttpResponse
from django.conf import settings
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404


from .models import Kinorium
from .models import MovieRSS
from .models import UserPreferences
from .parse import kinozal_scan

from movie_filter_pro.settings import HIGH, LOW, DEFER, SKIP, WAIT_TRANS, TRANS_FOUND
from .classes import LinkConstructor
from .parse import get_kinorium_first_search_results
from .parse import kinozal_search
from .util import log
from .util import get_cached_image_url
from .util import remove_cached_image

import random
@login_required()
@require_GET
def scan(request):
    """
    Вызывается при нажатии на кнопку Scan
    :param request:
    :return:
    """
    last_scan = UserPreferences.objects.get(user=request.user).last_scan
    context = {'last_scan': last_scan}
    user = request.user

    # pref, _ = UserPreferences.objects.get_or_create(user=user)
    pref = get_object_or_404(UserPreferences, user=user)
    start_page = pref.scan_from_page
    pref.scan_from_page = None
    pref.save(update_fields=['scan_from_page'])

    try:
        site = LinkConstructor(page=start_page)
        number_of_new_movies = kinozal_scan(site, last_scan, user)
    except Exception as e:
        log(f'ERROR! {e}')
    else:
        log(f"Scan complete,  add new: {number_of_new_movies}")

    # update last scan to now()
    UserPreferences.objects.filter(user=request.user).update(last_scan=datetime.now().date())

    messages.success(request, f'Added {number_of_new_movies} movies.')
    return HttpResponse(status=200)


def kinorium_table_data(request):
    movies = Kinorium.objects.all()
    return render(request, 'partials/kinorium-table.html', {'movies': movies})


@login_required()
def reset_rss(requst):
    # htmx function
    if requst.method == 'DELETE':
        rss = MovieRSS.objects.all()
        if rss:
            rss.delete()
        messages.success(requst, 'Success!')
        return HttpResponse(status=200)


@login_required()
def clear_log(request):
    log_type = request.GET.get('inlineRadioOptions')
    log_file_map = {
        'scan': settings.SCAN_LOG,
        'debug': settings.DEBUG_LOG,
        'error': settings.ERROR_LOG,
    }

    if log_type not in log_file_map:
        messages.error(request, f"Invalid log type: {log_type}")
        return HttpResponse(f"Invalid log type: {log_type}", status=400)

    log_file = log_file_map[log_type]
    print('log_file', log_file)

    try:
        if os.path.exists(log_file):
            with open(log_file, 'r+') as file:
                file.truncate(0)
        messages.success(request, 'Clear success!')
        return HttpResponse(status=200)
    except Exception as e:
        messages.error(request, f"Ошибка при очистке логов: {e}")
        return HttpResponse(status=500)


# @require_GET
# def rss_table_data(request):
#     prefs = UserPreferences.objects.get(user=request.user)
#     paginate_by = settings.INFINITE_PAGINATION_BY
#
#     if 'priority' in request.GET:
#         match request.GET['priority']:
#             case 'HIGH':
#                 priority = HIGH
#             case 'LOW':
#                 priority = LOW
#             case 'DEFER':
#                 priority = DEFER
#             case 'TRANS':
#                 priority = TRANS_FOUND
#     else:
#         raise Exception('No priority in request!')
#
#     # Получаем уже показанные ID из запроса
#     displayed_ids = request.GET.getlist('displayed_ids[]', [])
#     displayed_ids = [int(id) for id in displayed_ids if id.isdigit()]
#
#     movies_qs = MovieRSS.objects.filter(priority=priority)
#
#     # Исключаем уже показанные фильмы
#     if displayed_ids:
#         movies_qs = movies_qs.exclude(id__in=displayed_ids)
#
#     if 'reverse' in request.GET:
#         movies_qs = movies_qs.reverse()
#
#     if 'textfilter' in request.GET:
#         # print(f"FILTER by: {request.GET['textfilter']}")
#         movies_qs = movies_qs.filter(
#             Q(title__icontains=request.GET['textfilter']) |
#             Q(original_title__icontains=request.GET['textfilter']) |
#             Q(year__icontains=request.GET['textfilter'])
#         )
#
#     page_number = request.GET.get('page', 1)
#     log(f'LEN: {movies_qs.count()}', 'debug')
#     paginator = Paginator(movies_qs, paginate_by)
#     page_obj = paginator.get_page(page_number)
#
#     found_total = movies_qs.count()
#
#     # Cache images in the view
#     for f in page_obj:
#         f.poster_url = get_cached_image_url(f.poster, f.pk, f.priority)
#
#     context = {
#         "movies": page_obj,
#         "found_total": found_total
#     }
#
#     # debug
#     print('\nAdded:')
#     for m in page_obj:
#         print(f'\t{m}')
#
#     return render(request, 'partials/rss-table.html', context)

@require_GET
def rss_table_data(request):
    print('\nREQUEST NEW DATA')
    prefs = UserPreferences.objects.get(user=request.user)
    chunk_size = settings.INFINITE_PAGINATION_BY

    # Получаем приоритет
    if 'priority' in request.GET:
        match request.GET['priority']:
            case 'HIGH':
                priority = HIGH
            case 'LOW':
                priority = LOW
            case 'DEFER':
                priority = DEFER
            case 'TRANS':
                priority = TRANS_FOUND
    else:
        raise Exception('No priority in request!')

    # Получаем уже показанные ID
    displayed_ids_str = request.GET.get('displayed_ids', '')
    print(f'{displayed_ids_str=}')
    displayed_ids = [int(id) for id in displayed_ids_str.split(',') if id.isdigit()]
    print(f'{displayed_ids=}')

    # Основной QuerySet
    movies_qs = MovieRSS.objects.filter(priority=priority)

    # Фильтрация
    if displayed_ids:
        movies_qs = movies_qs.exclude(id__in=displayed_ids)

    if 'reverse' in request.GET:
        movies_qs = movies_qs.reverse()

    if 'textfilter' in request.GET:
        movies_qs = movies_qs.filter(
            Q(title__icontains=request.GET['textfilter']) |
            Q(original_title__icontains=request.GET['textfilter']) |
            Q(year__icontains=request.GET['textfilter'])
        )

    # Берём следующую порцию
    movies = movies_qs[:chunk_size]
    found_total = movies_qs.count()

    # Кэшируем изображения
    for movie in movies:
        movie.poster_url = get_cached_image_url(movie.poster, movie.pk, movie.priority)

    context = {
        "movies": movies,
        "found_total": found_total
    }

    # debug
    print('\nAdded:')
    for m in movies:
        print(f'\t{m}')

    return render(request, 'partials/rss-table.html', context)


@require_POST
@csrf_exempt
def ignore_movie(request, pk):
    try:
        MovieRSS.objects.filter(pk=pk).update(priority=SKIP)
        remove_cached_image(pk)
        messages.success(request, f"Hide: '{MovieRSS.objects.get(pk=pk).title}'")
        return HttpResponse(status=200)
    except:
        messages.error(request, f"Error with removing Movie pk={pk}")
        return HttpResponse(status=500)


@require_POST
def defer(request, pk):
    try:
        MovieRSS.objects.filter(pk=pk).update(priority=DEFER)
        messages.success(request, f"'{MovieRSS.objects.get(pk=pk).title}' defer successfully")
        return HttpResponse(status=200)
    except:
        messages.error(request, f"Error with defer Movie pk={pk}")
        return HttpResponse(status=500)


@require_POST
def wait_trains(request, pk):
    try:
        MovieRSS.objects.filter(pk=pk).update(priority=WAIT_TRANS)
        remove_cached_image(pk)
        messages.success(request, f"'{MovieRSS.objects.get(pk=pk).title}' add to Wait Trans successfully")
        return HttpResponse(status=200)
    except:
        messages.error(request, f"Error with Wait Trans, Movie pk={pk}")
        return HttpResponse(status=500)


@require_GET
def kinorium_search_111(request, kinozal_id: int):
    """
    Сначала выполняет поиск на кинориуме, берет первый результат и переходит по нему.
    По этой схеме Кинориум банит за поиск, поэтому выпилил этот подход.
    :param request:
    :param kinozal_id:
    :return:
    """
    m = MovieRSS.objects.get(id=kinozal_id)
    data = ' '.join([m.title, m.original_title, m.year])
    link = get_kinorium_first_search_results(data)
    return HttpResponse(link)


@require_GET
def kinorium_search(request, kinozal_id: int):
    """
    Просто выполняет поиск.
    Вырезает ненужные слова, заданные в настройках.
    """
    url = 'https://ru.kinorium.com/search/?q='
    m = MovieRSS.objects.get(id=kinozal_id)

    search_string = ' '.join([m.title, m.original_title, m.year])

    ignored_words_qs = UserPreferences.objects.get(user=request.user).ignore_title
    ignored_words = map(str.strip, ignored_words_qs.split(','))
    for w in ignored_words:
        search_string = search_string.replace(w, '')

    link = url + search_string

    return HttpResponse(link)



@require_GET
def kinozal_download(request, kinozal_id: int):

    found = kinozal_search(kinozal_id)

    context = {'found': found}
    return render(request, 'partials/kinozal_download.html', context)


def get_torrent_file(request, kinozal_id: int):
    cookie_pass = UserPreferences.objects.get(user=request.user).cookie_pass
    cookie_uid = UserPreferences.objects.get(user=request.user).cookie_uid
    destination = UserPreferences.objects.get(user=request.user).torrents_hotfolder

    out_of_torrent_number_message = 'Вам недоступен торрент-файл для скачивания'

    print('GET torrent', kinozal_id)
    # TODO Гвозди
    url = f"https://dl.kinozal.tv/download.php?id={kinozal_id}"
    print('LINK', url)

    headers = {'user-agent': "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/57.0.2987.98 Safari/537.36"}
    cookies = {'pass': cookie_pass, 'uid': cookie_uid}

    s = requests.Session()
    r = s.get(url, headers=headers, cookies=cookies)

    bad_sign = '<i class="bi bi-x-lg" style="color: red"></i>'
    good_sign = '<i class="bi bi-check-lg"></i>'

    if r.headers.get('Content-Type') != 'application/x-bittorrent':
        if out_of_torrent_number_message in r.content.decode('windows-1251'):
            messages.error(request, f"Too much torrents today!")
            return HttpResponse(bad_sign)
        else:
            messages.error(request, f"Kinozal return html instead torrent")
            return HttpResponse(bad_sign)

    if r.status_code != 200:
        messages.error(request, f"Bad kinozal response")
        return HttpResponse(bad_sign)

    try:
        filename = r.headers['content-disposition'].split('=')[1].strip('"')
        full_path = Path(destination) / filename
        with open(full_path, 'wb') as file:
            file.write(r.content)

        return HttpResponse(good_sign)
    except (FileNotFoundError, KeyError):
        messages.error(request, f"Unknown error, can't get torrent")
        return HttpResponse(bad_sign)





@login_required
def get_log(request, log_type):
    """
    Reads and returns the content of a specified log file.

    Args:
        request: The HTTP request object.
        log_type: The type of log ('error', 'debug', or 'scan').

    Returns:
        An HTTP response with the log file content.
    """
    log_file_map = {
        'error': 'error.log',
        'debug': 'debug.log',
        'scan': 'scan.log',
        # 'full': 'full.log',
        # 'short': 'short.log',
    }

    if log_type not in log_file_map:
        return HttpResponse(f"Invalid log type: {log_type}", status=400)

    log_filename = log_file_map[log_type]
    log_filepath = os.path.join(settings.BASE_DIR, 'logs', log_filename)

    if not os.path.exists(log_filepath):
        return HttpResponse(f"Log file not found: {log_filename}", status=404)

    try:
        with open(log_filepath, 'r') as f:
            log_content = f.read()
    except Exception as e:
        return HttpResponse(f"Error reading log file: {e}", status=500)

    return HttpResponse(log_content, content_type="text/plain")
