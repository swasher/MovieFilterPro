import dataclasses
import sys
import logging
from datetime import datetime

from django.db.models import Q
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.template.defaultfilters import safe
from django.contrib.auth.models import User
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST, require_GET
from django.core.paginator import Paginator


from .models import MovieRSS, Kinorium, UserPreferences
from .forms import PreferencesForm
from .parse_csv import parse_file_movie_list, parse_file_votes
from .forms import UploadCsvForm
from movie_filter_pro.settings import HIGH, LOW, DEFER, SKIP, WAIT_TRANS, TRANS_FOUND

logger = logging.getLogger('my_logger')


@login_required
def rss(request):
    last_scan = UserPreferences.objects.get(user=request.user).last_scan
    total_high = MovieRSS.objects.filter(priority=HIGH).count()
    total_low = MovieRSS.objects.filter(priority=LOW).count()
    total_defer = MovieRSS.objects.filter(priority=DEFER).count()
    total_skip = MovieRSS.objects.filter(priority=SKIP).count()
    total_wait_trans = MovieRSS.objects.filter(priority=WAIT_TRANS).count()
    total_trans_found = MovieRSS.objects.filter(priority=TRANS_FOUND).count()
    return render(request, template_name='rss.html',
                  context={'last_scan': last_scan, 'total_high': total_high, 'total_low': total_low,
                           'total_defer': total_defer, 'total_skip': total_skip,
                           'total_wait_trans': total_wait_trans, 'total_trans_found': total_trans_found})


@login_required()
def log(request):
    return render(request, template_name='log.html')


@login_required()
def user_preferences_update(request):
    user = User.objects.get(pk=request.user.pk)
    pref, _ = UserPreferences.objects.get_or_create(user=user)
    form = PreferencesForm(request.POST or None, instance=pref)

    if request.method == 'POST':
        if form.is_valid():
            # pref = UserPreferences.objects.get_or_create(user=request.user)
            pref.last_scan = form.cleaned_data['last_scan']
            pref.scan_from_page = form.cleaned_data['scan_from_page']
            pref.countries = form.cleaned_data['countries']
            pref.genres = form.cleaned_data['genres']
            pref.max_year = int(form.cleaned_data['max_year'])
            pref.min_rating = float(form.cleaned_data['min_rating']) 

            pref.low_countries = form.cleaned_data['low_countries']
            pref.low_genres = form.cleaned_data['low_genres']
            pref.low_max_year = int(form.cleaned_data['low_max_year'])
            pref.low_min_rating = float(form.cleaned_data['low_min_rating'])

            pref.plex_address = form.cleaned_data['plex_address']
            pref.plex_token = form.cleaned_data['plex_token']

            pref.save()
            return redirect(reverse('user_preferences'))
    return render(request, 'preferences_update_form.html', {'form': form})





@login_required()
def kinorium(request):
    htmx = request.htmx

    if htmx and htmx.target == 'dialog' and request.method == 'GET':
        form = UploadCsvForm(request.GET)
        return render(request, 'partials/upload_kinorium_form.html', {'form': form})

    if htmx and htmx.target == 'kinorium-table' and request.method == 'GET':
        query_text = request.GET.get('filter')
        movies = Kinorium.objects.filter(
            Q(title__contains=query_text) | 
            Q(original_title__contains=query_text) |
            Q(year__contains=query_text)
        )
        return render(request, 'partials/kinorium-table.html', {'movies': movies})

    if htmx and htmx.target == 'dialog' and request.method == 'POST':
        if 'file_votes' in request.FILES and 'file_movie_list' in request.FILES:

            print('\nСканируем "Списки фильмов"')
            dict_obj_with_spiski = parse_file_movie_list(request.FILES['file_movie_list'])
            if not dict_obj_with_spiski:
                return HttpResponse(safe("<b style='color:red'>Improper file!</b>"))
            print(f'-- Movies added: {len(dict_obj_with_spiski)}')

            print('\nСканируем "Просмотренные"')
            dict_obj_with_votes = parse_file_votes(request.FILES['file_votes'])
            if not dict_obj_with_votes:
                return HttpResponse(safe("<b style='color:red'>Improper file!</b>"))
            print(f'-- Movies added: {len(dict_obj_with_votes)}')

            objs = Kinorium.objects.all()
            objs.delete()

            list_of_KinoriumMovie_obj = [Kinorium(**dataclasses.asdict(vals)) for vals in dict_obj_with_spiski]
            Kinorium.objects.bulk_create(list_of_KinoriumMovie_obj)

            list_of_KinoriumMovie_obj = [Kinorium(**dataclasses.asdict(vals)) for vals in dict_obj_with_votes]
            Kinorium.objects.bulk_create(list_of_KinoriumMovie_obj)

            # return HttpResponse(safe("<b style='color:green'>Update success!</b>"))
            messages.success(request, 'Update success!')
            return HttpResponse(status=204)

        else:
            html = "<b style='color:red'>Need both files!</b>"
            return HttpResponse(safe(html))

    movies = Kinorium.objects.all()
    return render(request, 'kinorium.html', {'movies': movies})


def tst(request):
    if request.method == 'POST':
        print(request.POST)
    if request.method == 'GET':
        print(request.GET)

    if request.htmx:
        return HttpResponse('SOME HTMX DATA')
    else:
        return render(request, 'testing.html')
