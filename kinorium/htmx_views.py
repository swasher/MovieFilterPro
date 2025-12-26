from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.http import require_http_methods, require_GET, require_POST

from moviefilter.models import Kinorium
from moviefilter.models import MovieRSS
from moviefilter.models import UserPreferences


def kinorium_table_data(request):
    movies = Kinorium.objects.all()
    return render(request, 'partials/kinorium-table-data.html', {'movies': movies})


@require_GET
def kinorium_search(request, kinozal_id: int):
    """
    Просто выполняет поиск.
    Вырезает ненужные слова, заданные в настройках.
    """
    url = 'https://ru.kinorium.com/search/?q='
    m = MovieRSS.objects.get(id=kinozal_id)

    search_string = ' '.join([m.title, m.original_title, m.year])

    pref = UserPreferences.get()
    ignored_words_qs = pref.ignore_title
    ignored_words = map(str.strip, ignored_words_qs.split(','))
    for w in ignored_words:
        search_string = search_string.replace(w, '')

    link = url + search_string

    return HttpResponse(link)
