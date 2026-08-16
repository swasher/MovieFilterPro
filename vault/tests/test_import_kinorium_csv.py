from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Country
from vault.management.commands.import_kinorium_csv import Command, parse_date
from vault.models import Movie, UserListMovie, UserMovie


class ParseDateTest(TestCase):
    def test_parses_datetime_with_time(self):
        self.assertEqual(parse_date('2021-01-23 00:32:55'), date(2021, 1, 23))
        self.assertEqual(parse_date('2021-01-23 00:32'), date(2021, 1, 23))
        self.assertEqual(parse_date('2021-01-23'), date(2021, 1, 23))
        self.assertEqual(parse_date('23.01.2021'), date(2021, 1, 23))
        self.assertIsNone(parse_date(''))


class ImportDatesTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='import_user', id=1)
        self.movie = Movie.objects.create(title='Тест', year=2021)
        self.cmd = Command()
        self.cmd.stdout = type('Out', (), {'write': lambda *a, **k: None})()
        self.cmd.stderr = type('Out', (), {'write': lambda *a, **k: None})()
        self.cmd.style = type('S', (), {
            'SUCCESS': lambda self, m: m,
            'WARNING': lambda self, m: m,
            'ERROR': lambda self, m: m,
        })()
        Country.objects.get_or_create(name='Unknown', defaults={'code': 'XX'})

    def test_set_rating_stores_rated_at(self):
        self.cmd._set_rating(
            self.user, self.movie, 8,
            watched_at=date(2021, 1, 23), rated_at=date(2021, 1, 23),
        )
        um = UserMovie.objects.get(user=self.user, movie=self.movie)
        self.assertEqual(um.rating, 8)
        self.assertEqual(um.watch_status, UserMovie.WatchStatus.WATCHED)
        self.assertEqual(um.rated_at, date(2021, 1, 23))
        self.assertEqual(um.watched_at, date(2021, 1, 23))

    def test_set_rating_does_not_overwrite_existing_watched_at(self):
        self.cmd._set_watch_status(
            self.user, self.movie, UserMovie.WatchStatus.WATCHED, status_at=date(2020, 5, 1),
        )
        self.cmd._set_rating(
            self.user, self.movie, 7,
            watched_at=date(2021, 1, 23), rated_at=date(2021, 1, 23),
        )
        um = UserMovie.objects.get(user=self.user, movie=self.movie)
        self.assertEqual(um.watched_at, date(2020, 5, 1))
        self.assertEqual(um.rated_at, date(2021, 1, 23))

    def test_set_watch_status_stores_status_at(self):
        self.cmd._set_watch_status(
            self.user, self.movie, UserMovie.WatchStatus.PLAN, status_at=date(2021, 2, 1),
        )
        um = UserMovie.objects.get(user=self.user, movie=self.movie)
        self.assertEqual(um.watch_status, UserMovie.WatchStatus.PLAN)
        self.assertEqual(um.status_at, date(2021, 2, 1))

    def test_set_watch_status_watched_sets_watched_at(self):
        self.cmd._set_watch_status(
            self.user, self.movie, UserMovie.WatchStatus.WATCHED, status_at=date(2021, 3, 1),
        )
        um = UserMovie.objects.get(user=self.user, movie=self.movie)
        self.assertEqual(um.watched_at, date(2021, 3, 1))

    def test_set_favorite_stores_favorited_at(self):
        self.cmd._set_favorite(self.user, self.movie, favorited_at=date(2021, 4, 1))
        um = UserMovie.objects.get(user=self.user, movie=self.movie)
        self.assertTrue(um.is_favorite)
        self.assertEqual(um.favorited_at, date(2021, 4, 1))

    def test_append_movie_note_stores_note_at(self):
        self.cmd._append_movie_note(self.user, self.movie, 'Комментарий', note_at=date(2021, 5, 1))
        um = UserMovie.objects.get(user=self.user, movie=self.movie)
        self.assertEqual(um.note, 'Комментарий')
        self.assertEqual(um.note_at, date(2021, 5, 1))

    def test_add_to_custom_list_stores_added_at(self):
        self.cmd._add_to_custom_list(self.user, self.movie, 'Мой список', added_at=date(2021, 6, 1))
        relation = UserListMovie.objects.get(user_list__name='Мой список', movie=self.movie)
        self.assertEqual(relation.added_at.date(), date(2021, 6, 1))