from movie_filter_pro import wsgi
from moviefilter.models import MovieRSS
from movie_filter_pro.settings import HIGH, LOW, DEFER, SKIP, WAIT_TRANS

movies = MovieRSS.objects.all()

for m in movies:
    prio = LOW if m.low_priority else HIGH

    if m.ignored:
        prio = SKIP

    m.priority = prio
    m.save()
