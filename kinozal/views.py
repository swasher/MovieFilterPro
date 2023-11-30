import csv
import dataclasses
from io import StringIO
from datetime import date, datetime

from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.template.defaultfilters import safe
from django import forms
from django.contrib.auth.models import User
from django.urls import reverse
from django.contrib.auth.decorators import login_required

from .models import MovieRSS, KinoriumMovie, UserPreferences
from .classes import LinkConstructor
from kinozal.parse import parse_browse
from .checks import exist_in_kinorium, exist_in_kinozal, pass_all_filters
from .parse import get_details
from .models import MovieRSS


def movies(request):
    movies = MovieRSS.objects.all()
    return render(request, template_name='movies.html', context={'movies': movies})


def handle_uploaded_file(f):
    # with open("some/file/name.txt", "wb+") as destination:
    content = f.read()
    for line in content.lines():
        print(line)

def from_line(line: str) -> list[str]:
    return next(csv.reader([line]))

def upload_to_dictreader(requst_file):
    content = requst_file.read()
    data = content.decode('utf-16', 'strict')
    dict_reader_obj = csv.DictReader(StringIO(data, newline=''), delimiter='\t')
    return dict_reader_obj


def year_to_int(year: str) -> int:
    try:
        year = int(year)
    except:
        return HttpResponse(safe(f"<b style='color:red'>Year not string in {title}</b>"))
    return year


def upload_csv(request):
    if request.method == 'POST':

        if 'file_votes' in request.FILES and 'file_movie_list' in request.FILES:

            try:
                movie_lists_data = upload_to_dictreader(request.FILES['file_movie_list'])
                print('\nLists')
                for row in movie_lists_data:
                    title = row['Title']
                    original_title = row['Original Title']
                    t = row['Type']
                    year = year_to_int(row['Year'])
                    list_title = row['ListTitle']

                    print(list_title, title, original_title, t, year)

                    match list_title:
                        case 'Буду смотреть':
                            status = KinoriumMovie.WILL_WATCH
                        case 'Не буду смотреть':
                            status = KinoriumMovie.DECLINED
                        case _:
                            status = None

                    if t == 'Фильм' and status:
                        m, created = KinoriumMovie.objects.get_or_create(
                            title=title, original_title=original_title, year=year
                        )
                        m.status = status
                        m.save()
            except:
                return HttpResponse(safe("<b style='color:red'>Error processing Movie List file!</b>"))


            try:
                votes_data = upload_to_dictreader(request.FILES['file_votes'])
                print('\nVOTES')
                for row in votes_data:
                    title = row['Title']
                    original_title = row['Original Title']
                    t = row['Type']
                    year = year_to_int(row['Year'])
                    print(title, original_title, t, year)

                    if t == 'Фильм':
                        m, created = KinoriumMovie.objects.get_or_create(
                            title=title, original_title=original_title, year=year
                        )
                        m.status = KinoriumMovie.WATCHED
                        m.save()

            except Exception as e:
                return HttpResponse(safe(f"<b style='color:red'>Error processing Vote file! Error: {e}</b>"))

            return HttpResponse(safe("<b style='color:green'>Update success!</b>"))

        else:
            html = "<b style='color:red'>Need both files!</b>"
            return HttpResponse(safe(html))

    return render(request, 'upload_csv.html')


@login_required()
def scan_page(request):
    last_scan = UserPreferences.objects.get(user=request.user).last_scan
    return render(request, 'scan.html', {'last_scan': last_scan})


@login_required()
def scan(request):
    scan_to_date = UserPreferences.objects.get(user=request.user).last_scan
    site = LinkConstructor()

    movies = parse_browse(site, scan_to_date)

    for m in movies:
        """
        LOGIC:
        - если есть в базе kinozal - пропускаем (предложение о скачивании показывается пользователю один раз)
        - если есть в базе kinorium - пропускаем (любой статус в кинориуме, - просмотрено, буду смотреть, не буду смотреть)
            - проверяем также частичное совпадение, и тогда записываем в базу, а пользователю предлагаем установить связь через поля кинориума
        - если фильм прошел проверки по базам, тогда вытягиваем для него данные со страницы
        - проверяем через пользовательские фильтры
        - и вот теперь только заносим в базу 
        """
        if exist_in_kinozal(m):
            print(f'SKIP [kinozal]: {m.title} - {m.year}')
            continue

        if exist_in_kinorium(m):
            print(f'SKIP [kinorium]: {m.title} - {m.year}')
            continue

        print(f'GET DETAILS: {m.title} - {m.year}')
        m = get_details(m)

        if pass_all_filters(request.user, m):
            print(f'ADD TO DB: {m.title} - {m.year}')
            MovieRSS.objects.get_or_create(title=m.title, original_title=m.original_title, year=m.year,
                                           defaults=dataclasses.asdict(m))

    UserPreferences.objects.filter(user=request.user).update(last_scan=datetime.now().date())

    return render(request, 'scan.html', context={'movies': movies})


class PreferencesForm(forms.ModelForm):
    class Meta:
        model = UserPreferences
        fields = '__all__'

    # def clean_zoom(self):
    #     zoom = int(self.cleaned_data["zoom"])
    #     if zoom < 70 or zoom > 130:
    #         raise ValidationError("Zoom not in range [70-130]!")
    #
    #     # Always return a value to use as the new cleaned data, even if
    #     # this method didn't change it.
    #     return zoom


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
            pref.save()
            return redirect(reverse('kinozal:user_preferences'))
    return render(request, 'preferences_update_form.html', {'form': form})