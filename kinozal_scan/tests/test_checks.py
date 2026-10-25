from django.contrib.auth.models import User
from django.test import TestCase

from movie_filter_pro.settings import HIGH, LOW
from moviefilter.classes import KinozalMovie
from moviefilter.models import UserPreferences
from kinozal_scan.checks import check_users_filters


class CheckUsersFiltersGenreTests(TestCase):
    """Проверяет, что фильтр по жанрам не зависит от регистра и пробелов."""

    def setUp(self):
        self.user = User.objects.create_user(username="filter-user", password="secret")
        self.preferences = UserPreferences(user=self.user)
        self.preferences.countries = ""
        self.preferences.genres = "мюзикл, семейный"
        self.preferences.max_year = 1990
        self.preferences.min_rating = 3.0
        self.preferences.low_countries = ""
        self.preferences.low_genres = ""
        self.preferences.low_max_year = 2000
        self.preferences.low_min_rating = 5.0
        self.preferences.save()

    def _movie(self, genres: str) -> KinozalMovie:
        m = KinozalMovie(kinozal_id=1, title="t", original_title="o", year="2025")
        m.genres = genres
        m.countries = "США"
        m.kinopoisk_rating = 7.0
        m.imdb_rating = 7.0
        return m

    def test_lowercase_genre_is_blocked(self):
        self.assertFalse(check_users_filters(self.user, self._movie("Драма, семейный"), HIGH, self.preferences))

    def test_capitalized_genre_is_blocked(self):
        self.assertFalse(check_users_filters(self.user, self._movie("Комедия, Семейный"), HIGH, self.preferences))

    def test_genre_with_trailing_space_is_blocked(self):
        self.assertFalse(check_users_filters(self.user, self._movie("Мелодрама, семейный "), HIGH, self.preferences))

    def test_unrelated_genre_passes_high_filter(self):
        self.assertTrue(check_users_filters(self.user, self._movie("Боевик, триллер"), HIGH, self.preferences))

    def test_strict_genre_does_not_affect_low_filter(self):
        # В low_genres жанр не задан, поэтому фильтр LOW должен пропускать фильм.
        self.assertTrue(check_users_filters(self.user, self._movie("Комедия, Семейный"), LOW, self.preferences))
