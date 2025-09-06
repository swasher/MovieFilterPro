from django.contrib.auth.models import User
from moviefilter.models import MovieRSS


if __name__ == '__main__':
    user = User.objects.get(pk=1)
    movies = MovieRSS.objects.all()

    for m in movies:
        if m.imdb_rating == 10:
            print(m.title, m.imdb_rating)

            # if m.imdb_rating and m.imdb_rating < 7:
            m.imdb_rating = None
            m.save()
