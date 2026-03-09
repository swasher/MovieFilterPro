from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from vault.models import Movie
from vault.services.tmdb_movie_import_service import TMDBMovieImportService


class _FakeSearchResponse:
    def __init__(self, results):
        self.results = results


class _FakeTMDBClient:
    def __init__(self, movie_results=None, tv_results=None, movie_details=None, tv_details=None):
        self._movie_results = movie_results or []
        self._tv_results = tv_results or []
        self._movie_details = movie_details or {}
        self._tv_details = tv_details or {}

    def movie_search(self, query, include_adult=True):
        return _FakeSearchResponse(self._movie_results)

    def tv_search(self, query, include_adult=True):
        return _FakeSearchResponse(self._tv_results)

    def movie(self, movie_id):
        return self._movie_details[movie_id]

    def tv_show(self, tv_id):
        return self._tv_details[tv_id]

    def person(self, person_id):
        raise KeyError(person_id)


def _movie_details(tmdb_id=321, title="Интерстеллар"):
    return SimpleNamespace(
        id=tmdb_id,
        title=title,
        original_title="Interstellar",
        overview="Space travel",
        release_date=date(2014, 11, 7),
        runtime=169,
        poster_path="/poster.jpg",
        popularity=98.0,
        vote_average=8.7,
        budget=165000000,
        revenue=701729206,
        status="Released",
        videos=[],
        genres=[],
        countries=[],
        origin_countries=[],
        cast=[],
        crew=[],
    )


class TMDBMovieImportServiceSearchTests(SimpleTestCase):
    @patch("vault.services.tmdb_movie_import_service.get_tmdb_client")
    def test_search_merges_movie_and_tv_results(self, get_tmdb_client_mock):
        fake_tmdb = _FakeTMDBClient(
            movie_results=[
                SimpleNamespace(
                    id=101,
                    title="Дюна",
                    original_title="Dune",
                    release_date=date(2021, 9, 3),
                    poster_path="/dune.jpg",
                    popularity=100.0,
                    vote_average=8.2,
                )
            ],
            tv_results=[
                SimpleNamespace(
                    id=202,
                    name="Фарго",
                    original_name="Fargo",
                    first_air_date=date(2014, 4, 15),
                    poster_path="/fargo.jpg",
                    popularity=70.0,
                    vote_average=8.8,
                )
            ],
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        results = TMDBMovieImportService.search_movies("du", limit=10)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].media_type, "movie")
        self.assertEqual(results[0].tmdb_id, 101)
        self.assertEqual(results[1].media_type, "tv")
        self.assertEqual(results[1].tmdb_id, 202)


class TMDBMovieImportServiceTests(TestCase):
    @patch("vault.services.tmdb_movie_import_service.get_tmdb_client")
    @patch("vault.services.tmdb_movie_sync_service.get_tmdb_client")
    def test_import_creates_movie_and_generates_unique_slug(self, sync_get_tmdb_client_mock, get_tmdb_client_mock):
        Movie.objects.create(
            title="Интерстеллар",
            original_title="Interstellar",
            year=2014,
            movie_type=Movie.MovieType.MOVIE,
            status=Movie.Status.RELEASED,
        )

        fake_tmdb = _FakeTMDBClient(movie_details={321: _movie_details()})
        get_tmdb_client_mock.return_value = fake_tmdb
        sync_get_tmdb_client_mock.return_value = fake_tmdb

        result = TMDBMovieImportService.import_movie(321, "movie")

        self.assertEqual(result.status, "created")
        self.assertEqual(result.movie.tmdb_id, 321)
        self.assertEqual(result.movie.tmdb_media_type, "movie")
        self.assertEqual(result.movie.title, "Интерстеллар")
        self.assertTrue(result.movie.slug.endswith("-2"))

    @patch("vault.services.tmdb_movie_import_service.get_tmdb_client")
    @patch("vault.services.tmdb_movie_sync_service.get_tmdb_client")
    def test_import_returns_existing_movie_for_same_tmdb_id(self, sync_get_tmdb_client_mock, get_tmdb_client_mock):
        existing_movie = Movie.objects.create(
            title="Дюна",
            original_title="Dune",
            year=2021,
            movie_type=Movie.MovieType.MOVIE,
            status=Movie.Status.RELEASED,
            tmdb_id=321,
            tmdb_media_type="movie",
        )

        result = TMDBMovieImportService.import_movie(321, "movie")

        self.assertEqual(result.status, "exists")
        self.assertEqual(result.movie.id, existing_movie.id)
        get_tmdb_client_mock.assert_not_called()
        sync_get_tmdb_client_mock.assert_not_called()
