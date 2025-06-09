from movie_filter_pro import wsgi
from moviefilter.classes import LinkConstructor
from datetime import date
import dataclasses
from django.contrib.auth.models import User
from moviefilter.models import MovieRSS
from moviefilter.parse import parse_page, movie_audit
from moviefilter.checks import exist_in_kinorium
from django.core.exceptions import ObjectDoesNotExist
from movie_filter_pro.settings import HIGH, LOW, DEFER, SKIP, WAIT_TRANS

if __name__ == '__main__':
    user = User.objects.get(pk=1)
    movies = MovieRSS.objects.all()

    for m in movies:
        if m.imdb_rating == 10:
            print(m.title, m.imdb_rating)

            # if m.imdb_rating and m.imdb_rating < 7:
            m.imdb_rating = None
            m.save()
