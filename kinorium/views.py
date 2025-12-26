import dataclasses

from django.db.models import Q
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.template.defaultfilters import safe
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from moviefilter.models import MovieRSS, Kinorium, UserPreferences
from .parse_csv import parse_file_movie_list, parse_file_votes
from .forms import UploadCsvForm


@login_required()
def table(request):
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
        return render(request, 'partials/kinorium-table-data.html', {'movies': movies})

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
    return render(request, 'kinorium-table.html', {'movies': movies})
