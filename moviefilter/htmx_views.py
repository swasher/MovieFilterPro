import os
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib import messages
from django.http import HttpResponse
from django.conf import settings
from django.views.decorators.http import require_http_methods, require_GET

from .models import Kinorium
from .models import MovieRSS
from .models import UserPreferences
from django.core.paginator import Paginator

from movie_filter_pro.settings import HIGH, LOW, DEFER, SKIP


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
    print(request.GET)

    if 'priority' in request.GET:
        match request.GET['priority']:
            case 'HIGH':
                priority = HIGH
            case 'LOW':
                priority = LOW
            case 'DEFER':
                priority = DEFER
    else:
        priority = HIGH

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
    paginator = Paginator(movies_qs, paginate_by)
    page_obj = paginator.get_page(page_number)

    found_total = movies_qs.count()

    return render(request, 'partials/rss-table.html',
                  {'movies': page_obj, 'priority': priority, 'found_total': found_total})


def ignore_movie(request, pk):
    # htmx
    if request.method == 'DELETE':
        try:
            MovieRSS.objects.filter(pk=pk).update(priority=SKIP)
            messages.success(request, f"'{MovieRSS.objects.get(pk=pk).title}' remove successfully")
            return HttpResponse(status=200)
        except:
            messages.error(request, f"Error with removing Movie pk={pk}")
            return HttpResponse(status=500)


def defer(request, pk):
    # htmx
    if request.method == 'POST':
        try:
            MovieRSS.objects.filter(pk=pk).update(priority=DEFER)
            messages.success(request, f"'{MovieRSS.objects.get(pk=pk).title}' defer successfully")
            return HttpResponse(status=200)
        except:
            messages.error(request, f"Error with defer Movie pk={pk}")
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
