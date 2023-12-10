from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib import messages
from django.http import HttpResponse

from .models import Kinorium
from .models import MovieRSS
from .models import UserPreferences
from django.core.paginator import Paginator


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


def rss_table_data(request, prio='normal_priority'):
    if prio == 'normal_priority':
        movies_qs = MovieRSS.objects.filter(low_priority=False, ignored=False)
    else:
        movies_qs = MovieRSS.objects.filter(low_priority=True, ignored=False)

    prefs = UserPreferences.objects.get(user=request.user)
    paginate_by = prefs.paginate_by

    paginator = Paginator(movies_qs, paginate_by)
    page_number = request.GET.get("page")
    movies_page = paginator.get_page(page_number)

    return render(request, 'partials/rss-table.html', {'movies': movies_page})