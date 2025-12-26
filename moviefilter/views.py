from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from .models import MovieRSS, Kinorium, UserPreferences
from movie_filter_pro.settings import HIGH, LOW, DEFER, SKIP, WAIT_TRANS, TRANS_FOUND


@login_required
def rss(request):
    pref = UserPreferences.get()
    last_scan = pref.last_scan

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
