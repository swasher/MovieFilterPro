"""Порядок каста на странице сериала.

TMDB не даёт сериалам надёжного billing order, поэтому личные метки
(любимый/звезда) поднимают актёра выше титров. Для фильмов порядок остаётся
как отдаёт TMDB.
"""

from django.contrib.auth.models import User
from django.test import Client, TestCase

from vault.models import FavoritePerson, Movie, MoviePerson, Person, StarPerson


class MovieCastOrderApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="cast_order", password="x")
        self.client.force_login(self.user)

        self.lead = Person.objects.create(
            tmdb_id="80001", imdb_id="nm8000001", name="Эмма Коррин", original_name="Emma Corrin"
        )
        self.second = Person.objects.create(
            tmdb_id="80002", imdb_id="nm8000002", name="Брит Марлинг", original_name="Brit Marling"
        )
        self.star = Person.objects.create(
            tmdb_id="80003", imdb_id="nm8000003", name="Клайв Оуэн", original_name="Clive Owen"
        )

        FavoritePerson.objects.create(user=self.user, person=self.star)
        StarPerson.objects.create(user=self.user, person=self.second)

    def _movie(self, movie_type, media_type):
        movie = Movie.objects.create(
            title="Убийство на краю света",
            original_title="A Murder at the End of the World",
            year=2023,
            movie_type=movie_type,
            tmdb_media_type=media_type,
        )
        for order, person in enumerate([self.lead, self.second, self.star]):
            MoviePerson.objects.create(
                movie=movie, person=person, role="actor", order=order
            )
        return movie

    def _actor_names(self, slug):
        response = self.client.get(f"/api/vault/movies/{slug}")
        self.assertEqual(response.status_code, 200)
        return [item["name"] for item in response.json()["actors"]]

    def test_series_hoists_favorite_and_star_actors(self):
        movie = self._movie(Movie.MovieType.MINISERIES, "tv")

        self.assertEqual(
            self._actor_names(movie.slug),
            ["Клайв Оуэн", "Брит Марлинг", "Эмма Коррин"],
        )

    def test_movies_keep_tmdb_order(self):
        movie = self._movie(Movie.MovieType.MOVIE, "movie")

        self.assertEqual(
            self._actor_names(movie.slug),
            ["Эмма Коррин", "Брит Марлинг", "Клайв Оуэн"],
        )

    def test_marks_do_not_leak_to_other_users(self):
        movie = self._movie(Movie.MovieType.SERIES, "tv")
        other = User.objects.create_user(username="other_user", password="x")
        self.client.force_login(other)

        self.assertEqual(
            self._actor_names(movie.slug),
            ["Эмма Коррин", "Брит Марлинг", "Клайв Оуэн"],
        )
