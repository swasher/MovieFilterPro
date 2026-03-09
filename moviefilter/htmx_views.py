from bs4 import BeautifulSoup
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib import messages
from django.http import HttpResponse
from django.conf import settings
from django.views.decorators.http import require_http_methods, require_GET, require_POST

from movie_filter_pro.settings import HIGH, LOW, DEFER, SKIP, WAIT_TRANS, TRANS_FOUND
from web_logger import log, LogType
from .models import MovieRSS
from .models import UserPreferences
from .hotfolder import resolve_torrents_hotfolder_path
from .image_caching import get_cached_image_url
from .image_caching import remove_cached_image
from .kinozal import LinkConstructor
from .kinozal import KinozalClient
from .classes import KinozalSearch
from .services.torrent_download_service import TorrentDownloadError, download_torrent_file
from vault.services.kinozal_download_import_service import KinozalDownloadImportService


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
@login_required()
def kinozal_download(request, kinozal_id: int):
    """
    Запускается при клике на кнопку "Download"
    :param request:
    :param kinozal_id:
    :return:
    """
    found = kinozal_search(kinozal_id)

    context = {
        'found': found,
        'movie_rss_id': kinozal_id,
    }
    return render(request, 'partials/kinozal_download.html', context)


@require_POST
@login_required()
def get_torrent_file(request, kinozal_id: int):
    bad_sign = '<i class="bi bi-x-lg" style="color: red"></i>'
    good_sign = '<i class="bi bi-check-lg"></i>'
    movie_rss_id_raw = request.POST.get('movie_rss_id')
    try:
        movie_rss_id = int(movie_rss_id_raw)
    except (TypeError, ValueError):
        messages.error(request, "Не передан исходный MovieRSS для post-download обработки.")
        return HttpResponse(bad_sign)

    print('GET torrent', kinozal_id, movie_rss_id)

    try:
        result = download_torrent_file(kinozal_id)
        queue_result = KinozalDownloadImportService.enqueue_successful_download(
            movie_rss_id=movie_rss_id,
            torrent_id=kinozal_id,
            user=request.user,
            saved_to=result.saved_to,
        )
        if queue_result.status == "queued":
            messages.success(request, queue_result.message)
        else:
            messages.warning(request, queue_result.message)
        return HttpResponse(good_sign)
    except TorrentDownloadError as exc:
        error_message = exc.message
        if exc.hint:
            error_message = f"{error_message} {exc.hint}"
        messages.error(request, error_message)
        return HttpResponse(bad_sign)
    except Exception as e:
        messages.error(request, f"Unexpected error: {str(e)}")
        return HttpResponse(bad_sign)


def kinozal_search(kinozal_id: int):
    """
    Принимает фильм на входе, и ищет на кинозале разновидности этого фильма. Используется для
    таблички Download где можно выбрать подходящую версию.
    :param kinozal_domain: текущий рабочий домен кинозала (только домен, типа 'kinozal.tv')
    :param kinozal_id:
    :return:
    """
    client = KinozalClient()
    pref = UserPreferences.get()

    m = MovieRSS.objects.get(id=kinozal_id)
    results = []

    combined_titles = ' / '.join([m.title, m.original_title])
    if len(combined_titles) < 64:
        search_string = combined_titles
    else:
        search_string = m.title

    try:
        year = str(int(m.year))
    except ValueError:
        year = None

    V_HD = 3  # Рипы HD(1080 и 720)
    V_4K = 7  # 4K

    for quality in [V_HD, V_4K]:

        if year:
            link_builder = LinkConstructor(s=search_string, d=year, v=quality)
        else:
            link_builder = LinkConstructor(s=search_string, v=quality)
        # for TERMINATOR, l = "https://kinozal.tv/browse.php?s=%F2%E5%F0%EC%E8%ED%E0%F2%EE%F0&g=0&c=1002&v=7&d=2019&w=0&t=0&f=0"

        response = client.get_html_response(link_builder.search_url())
        log(f'GRAB URL: {link_builder.search_url()}')

        if response.ok:
            soup = BeautifulSoup(response.content, "html.parser")
            movies_elements = soup.find_all('tr', 'bg')

            for element in movies_elements:
                m = KinozalSearch()

                m.id = element.a['href'].split('=')[1]
                m.header = element.a.text
                m.size = element.find_all('td', 's')[1].text
                m.seed = element.find('td', {'class': 'sl_s'}).text
                m.peer = element.find('td', {'class': 'sl_p'}).text
                m.created = element.find_all('td', 's')[2].text
                m.link = f'https://{pref.kinozal_domain}{element.a['href']}'
                m.is_4k = True if quality == V_4K else False
                m.is_sdr = True if 'SDR' in m.header else False

                results.append(m)

        else:
            raise Exception(f'ERROR: {response.content}')

    return results



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
