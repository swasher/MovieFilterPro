import os
import requests
from datetime import datetime
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib import messages
from django.http import HttpResponse
from django.conf import settings
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.core.paginator import Paginator

from .models import Kinorium
from .models import MovieRSS
from .models import UserPreferences
from .parse import kinozal_scan

from movie_filter_pro.settings import HIGH, LOW, DEFER, SKIP, WAIT_TRANS
from .classes import LinkConstructor
from .parse import get_kinorium_first_search_results
from .parse import kinozal_search


@login_required()
@require_GET
def scan(request):
    last_scan = UserPreferences.objects.get(user=request.user).last_scan
    context = {'last_scan': last_scan}
    user = request.user

    pref, _ = UserPreferences.objects.get_or_create(user=user)
    start_page = pref.scan_from_page

    site = LinkConstructor(page=start_page)
    counter = kinozal_scan(site, last_scan, user)

    # update last scan to now()
    UserPreferences.objects.filter(user=request.user).update(last_scan=datetime.now().date())

    messages.success(request, f'Added {counter} movies.')
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


@require_GET
def rss_table_data(request):
    prefs = UserPreferences.objects.get(user=request.user)
    paginate_by = settings.INFINITE_PAGINATION_BY

    if 'priority' in request.GET:
        match request.GET['priority']:
            case 'HIGH':
                priority = HIGH
            case 'LOW':
                priority = LOW
            case 'DEFER':
                priority = DEFER
    else:
        raise Exception('No priority in request!')

    movies_qs = MovieRSS.objects.filter(priority=priority)

    if 'reverse' in request.GET:
        movies_qs = movies_qs.reverse()

    if 'textfilter' in request.GET:
        movies_qs = movies_qs.filter(
            Q(title__icontains=request.GET['textfilter']) |
            Q(original_title__icontains=request.GET['textfilter']) |
            Q(year__icontains=request.GET['textfilter'])
        )

    page_number = request.GET.get('page', 1)
    print('LEN:', movies_qs.count())
    paginator = Paginator(movies_qs, paginate_by)
    page_obj = paginator.get_page(page_number)

    found_total = movies_qs.count()

    return render(request, 'partials/rss-table.html',
                  {'movies': page_obj, 'priority': priority, 'found_total': found_total})


@require_POST
def ignore_movie(request, pk):
    # DEPRECATED
    # request.session['count_movies_in_table'] = request.session.get('count_movies_in_table') - 1

    try:
        MovieRSS.objects.filter(pk=pk).update(priority=SKIP)
        messages.success(request, f"'{MovieRSS.objects.get(pk=pk).title}' remove successfully")
        return HttpResponse(status=200)
    except:
        messages.error(request, f"Error with removing Movie pk={pk}")
        return HttpResponse(status=500)


@require_POST
def defer(request, pk):
    # DEPRECATED
    # request.session['count_movies_in_table'] = request.session.get('count_movies_in_table') - 1

    try:
        MovieRSS.objects.filter(pk=pk).update(priority=DEFER)
        messages.success(request, f"'{MovieRSS.objects.get(pk=pk).title}' defer successfully")
        return HttpResponse(status=200)
    except:
        messages.error(request, f"Error with defer Movie pk={pk}")
        return HttpResponse(status=500)


@require_POST
def wait_trains(request, pk):
    # DEPRECATED
    # request.session['count_movies_in_table'] = request.session.get('count_movies_in_table') - 1

    try:
        MovieRSS.objects.filter(pk=pk).update(priority=WAIT_TRANS)
        messages.success(request, f"'{MovieRSS.objects.get(pk=pk).title}' add to Wait Trans successfully")
        return HttpResponse(status=200)
    except:
        messages.error(request, f"Error with Wait Trans, Movie pk={pk}")
        return HttpResponse(status=500)


def get_log(request, logtype):
    # import datetime
    # def write_to_file(file_path, content):
    #     with open(file_path, 'a') as file:
    #         file.write(content)
    #
    # # Пример использования
    # file_path = 'media/logs/' + 'full' + '.log'
    # content = str(datetime.datetime.now())+'\n'
    # write_to_file(file_path, content)

    if logtype in ['full', 'short', 'error']:
        file_path = os.path.join('logs', f'{logtype}.log')
        with open(file_path, 'r') as file:
            log = file.read().split('\n')
            log = '\n'.join(list(reversed(log)))
    else:
        raise Exception('Unknown logtype')

    return render(request, template_name='partials/log-content.html', context={'log': log})


@require_GET
def kinorium_search(request, kinozal_id: int):
    m = MovieRSS.objects.get(id=kinozal_id)
    data = ' '.join([m.title, m.original_title, m.year])
    link = get_kinorium_first_search_results(data)
    return HttpResponse(link)


@require_GET
def kinozal_download(request, kinozal_id: int):

    found = kinozal_search(kinozal_id)

    context = {'found': found}
    return render(request, 'partials/kinozal_download.html', context)


def get_torrent_file(request, kinozal_id: int):
    # todo move it to user preferencies
    cookie_pass = 'c1WSjB9vRK'
    cookie_uid = '19200863'
    destination = '//qnap/Torrents/'

    print('GET torrent', kinozal_id)
    url = f"https://dl.kinozal.tv/download.php?id={kinozal_id}"
    print('LINK', url)

    headers = {'user-agent': "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/57.0.2987.98 Safari/537.36"}
    cookies = {'pass': cookie_pass, 'uid': cookie_uid}

    s = requests.Session()
    r = s.get(url, headers=headers, cookies=cookies)

    bad_sign = '<i class="bi bi-x-lg" style="color: red"></i>'
    good_sign = '<i class="bi bi-check-lg"></i>'

    if r.status_code != 200:
        return HttpResponse(bad_sign)

    try:
        filename = r.headers['content-disposition'].split('=')[1].strip('"')
        with open(destination+filename, 'wb') as file:
            file.write(r.content)

        return HttpResponse(good_sign)
    except FileNotFoundError:
        return HttpResponse(bad_sign)


