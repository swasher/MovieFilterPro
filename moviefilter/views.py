import dataclasses
from datetime import datetime

from django.db.models import Q
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.template.defaultfilters import safe
from django.contrib.auth.models import User
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from plexapi.server import PlexServer
from silk.profiling.profiler import silk_profile

from .models import MovieRSS, Kinorium, UserPreferences
from .classes import LinkConstructor
from .forms import PreferencesForm
from .parse_csv import parse_file_movie_list, parse_file_votes
from .forms import UploadCsvForm
from .parse import kinozal_scan


@silk_profile(name='AAA')
@login_required
def movies(request):
    last_scan = UserPreferences.objects.get(user=request.user).last_scan
    return render(request, template_name='rss.html', context={'last_scan': last_scan})


@login_required()
def scan(request):
    last_scan = UserPreferences.objects.get(user=request.user).last_scan
    context = {'last_scan': last_scan}
    user = request.user

    if request.method == 'GET':

        site = LinkConstructor()
        movies = kinozal_scan(site, last_scan, user)




        UserPreferences.objects.filter(user=request.user).update(last_scan=datetime.now().date())

        movies = MovieRSS.objects.filter(low_priority=False, ignored=False)
        paginator = Paginator(movies, 5)
        page_number = request.GET.get("page")
        movies_page = paginator.get_page(page_number)
        context['movies'] = movies_page
        return render(request, 'partials/rss-table.html', context)

def user_preferences_update(request):
    user = User.objects.get(pk=request.user.pk)
    pref, _ = UserPreferences.objects.get_or_create(user=user)
    form = PreferencesForm(request.POST or None, instance=pref)

    if request.method == 'POST':
        if form.is_valid():
            # pref = UserPreferences.objects.get_or_create(user=request.user)
            pref.last_scan = form.cleaned_data['last_scan']
            pref.paginate_by = form.cleaned_data['paginate_by']
            pref.countries = form.cleaned_data['countries']
            pref.genres = form.cleaned_data['genres']
            pref.max_year = int(form.cleaned_data['max_year'])
            pref.min_rating = float(form.cleaned_data['min_rating']) 

            pref.low_countries = form.cleaned_data['low_countries']
            pref.low_genres = form.cleaned_data['low_genres']
            pref.low_max_year = int(form.cleaned_data['low_max_year'])
            pref.low_min_rating = float(form.cleaned_data['low_min_rating'])
            pref.save()
            return redirect(reverse('user_preferences'))
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
