import os
import uuid
from asgiref.sync import async_to_sync

from datetime import datetime
from pathlib import Path
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib import messages
from django.http import HttpResponse
from django.conf import settings
from django.views.decorators.http import require_http_methods, require_GET, require_POST

from .models import Kinorium
from .models import MovieRSS
from .models import UserPreferences
from .parse import kinozal_scan
from .exceptions import DetailsFetchError

from movie_filter_pro.settings import HIGH, LOW, DEFER, SKIP, WAIT_TRANS, TRANS_FOUND
from moviefilter.kinozal import LinkConstructor
from .parse import kinozal_search
from web_logger import log, LogType
from .image_caching import get_cached_image_url
from .image_caching import remove_cached_image
from .kinozal import KinozalClient
from .runtime import cancel_events, tasks
from .service import start_scan_task


# @login_required()
# @require_GET
# def scan(request):
#     """
#     Вызывается при нажатии на кнопку Scan
#     :param request:
#     :return:
#     """
#     pref = UserPreferences.get()
#     last_scan = pref.last_scan
#     start_page = pref.scan_from_page
#     user = request.user
#
#     # TODO Сдлать функцию-проверку всех необходимых параметров в preferences, если чего-то не хвататет, рисовать красный алерт.
#
#     try:
#         number_of_new_movies = kinozal_scan(start_page, last_scan, user)
#     except DetailsFetchError:
#         # Эта ошибка уже залогирована на более низком уровне с полным traceback.
#         # Здесь мы просто сообщаем пользователю о проблеме.
#         messages.error(request, 'Сканирование прервано. Не удалось получить данные со страницы фильма. Возможно, сайт недоступен или IP заблокирован. Проверьте error.log для деталей.')
#         return HttpResponse(status=500)
#     except Exception as e:
#         # Ловим любые другие непредвиденные ошибки
#         log(f'An unexpected error occurred in the scan view: {e}', logger_name=LogType.ERROR)
#         messages.error(request, f'Произошла непредвиденная ошибка: {e}')
#         return HttpResponse(status=500)
#     else:
#         log(f"Scan complete, new entries: {number_of_new_movies}")
#         pref.scan_from_page = None
#         pref.save()
#
#         # update last scan to now()
#         # UserPreferences.objects.filter(user=request.user).update(last_scan=datetime.now().date())
#         UserPreferences.objects.filter(pk=1).update(last_scan=datetime.now().date())
#
#         messages.success(request, f'Added {number_of_new_movies} movies.')
#         return HttpResponse(status=200)

@login_required
@require_GET
def scan(request):
    pref = UserPreferences.get()

    task_id = uuid.uuid4().hex
    user = request.user

    async_to_sync(start_scan_task)(
        task_id=task_id,
        start_page=pref.scan_from_page or 0,
        scan_to_date=pref.last_scan,
        user=user,
    )

    return HttpResponse(
        status=202,
        headers={
            "X-Task-ID": task_id
        }
    )


@require_POST
def cancel_scan(request, task_id):
    print('Scan was canceled by user.')
    event = cancel_events.get(task_id)
    if event:
        event.set()

    task = tasks.get(task_id)
    if task:
        task.cancel()  # ускоряет завершение await

    return HttpResponse(status=204)


@login_required()
def reset_rss(requst):
    # htmx function
    if requst.method == 'DELETE':
        rss = MovieRSS.objects.all()
        if rss:
            rss.delete()
        messages.success(requst, 'Success!')
        return HttpResponse(status=200)


@require_GET
def rss_table_data(request):
    print('\nREQUEST NEW DATA')
    chunk_size = settings.INFINITE_PAGINATION_BY

    # Получаем приоритет
    if 'priority' not in request.GET:
        raise Exception('No priority in request!')

    level = request.GET['priority']
    match level:
        case 'HIGH':
            priority = HIGH
        case 'LOW':
            priority = LOW
        case 'DEFER':
            priority = DEFER
        case 'TRANS':
            priority = TRANS_FOUND
        case _:
            raise Exception('Unknown priority value!')

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

    # Получаем домен из настроек текущего пользователя
    pref = UserPreferences.get()
    kinozal_domain = pref.kinozal_domain
    if not kinozal_domain:
        messages.error(request, "Нужно ввести домен kinozal в настройках")
        return HttpResponse(status=500)

    # Кэшируем изображения и добавляем ссылки (при нажатии выполняется поиск на kinozal по текущему фильму)
    for movie in movies:
        movie.poster_url = get_cached_image_url(movie.poster, movie.pk, movie.priority)
        link_constructor = LinkConstructor(s=f'{movie.title} / {movie.original_title}', d=f'{movie.year}', c=1002, v=3)
        movie.kinozal_search_link = link_constructor.search_url()

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
def kinozal_download(request, kinozal_id: int):
    """
    Запускается при клике на кнопку "Download"
    :param request:
    :param kinozal_id:
    :return:
    """
    found = kinozal_search(kinozal_id)

    context = {'found': found}
    return render(request, 'partials/kinozal_download.html', context)


# def get_torrent_file(request, kinozal_id: int):
#     prefs = UserPreferences.get()
#     cookie_pass = prefs.cookie_pass
#     cookie_uid = prefs.cookie_uid
#     destination = prefs.torrents_hotfolder
#     kinozal_domain = prefs.kinozal_domain
#
#     out_of_torrent_number_message = 'Вам недоступен торрент-файл для скачивания'
#
#     print('GET torrent', kinozal_id)
#
#     url = f"https://dl.{kinozal_domain}/download.php?id={kinozal_id}"
#     print('LINK', url)
#
#     headers = {'user-agent': "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/57.0.2987.98 Safari/537.36"}
#     cookies = {'pass': cookie_pass, 'uid': cookie_uid}
#
#     s = requests.Session()
#     r = s.get(url, headers=headers, cookies=cookies)
#
#     bad_sign = '<i class="bi bi-x-lg" style="color: red"></i>'
#     good_sign = '<i class="bi bi-check-lg"></i>'
#
#     if r.headers.get('Content-Type') != 'application/x-bittorrent':
#         if out_of_torrent_number_message in r.content.decode('windows-1251'):
#             messages.error(request, f"Too much torrents today!")
#             return HttpResponse(bad_sign)
#         else:
#             messages.error(request, f"Kinozal return html instead torrent")
#             return HttpResponse(bad_sign)
#
#     if r.status_code != 200:
#         messages.error(request, f"Bad kinozal response")
#         return HttpResponse(bad_sign)
#
#     try:
#         filename = r.headers['content-disposition'].split('=')[1].strip('"')
#         full_path = Path(destination) / filename
#         with open(full_path, 'wb') as file:
#             file.write(r.content)
#
#         return HttpResponse(good_sign)
#     except (FileNotFoundError, KeyError):
#         messages.error(request, f"Unknown error, can't get torrent")
#         return HttpResponse(bad_sign)

def get_torrent_file(request, kinozal_id: int):
    client = KinozalClient()
    pref = UserPreferences.get()

    destination = pref.torrents_hotfolder

    out_of_torrent_number_message = 'Вам недоступен торрент-файл для скачивания'

    print('GET torrent', kinozal_id)

    r = client.download_torrent(kinozal_id)

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
    except (FileNotFoundError, OSError) as e:
        # Ловим конкретные ошибки файловой системы
        messages.error(request, f"File system error: {str(e)}")
        return HttpResponse(bad_sign)
    except KeyError:
        messages.error(request, "Unknown error, can't get torrent filename")
        return HttpResponse(bad_sign)
    except Exception as e:
        # Общая обработка других ошибок
        messages.error(request, f"Unexpected error: {str(e)}")
        return HttpResponse(bad_sign)





def total_downloads_for_movie(request):
    # Получаем pk из GET-параметров, которые передаются через hx-vars
    pk = request.GET.get('pk')
    if not pk:
        return HttpResponse("", status=400)  # Плохой запрос, если pk отсутствует

    found = kinozal_search(pk)
    torrents_count = len(found)
    # return HttpResponse(download_count)

    if torrents_count <= 2:
        style_class = "secondary"
    elif torrents_count <= 6:
        style_class = "primary"
    else:
        style_class = "danger"

    htmx_string = f'<span class="badge text-bg-{style_class}">DOWNLOADS: {torrents_count}</span>'
    return HttpResponse(htmx_string)
