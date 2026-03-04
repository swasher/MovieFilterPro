from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from vault.models import Movie
from vault.services.tmdb_movie_matching_service import TMDBMovieMatchingService


class _FakeSearchResponse:
    def __init__(self, results):
        self.results = results


class _FakeTMDB:
    def __init__(self, movie_results=None, tv_results=None, movie_details=None, tv_details=None):
        self._movie_results = movie_results or []
        self._tv_results = tv_results or []
        self._movie_details = movie_details or {}
        self._tv_details = tv_details or {}

    def movie_search(self, query, include_adult=True, primary_release_year=None):
        return _FakeSearchResponse(self._movie_results)

    def tv_search(self, query, include_adult=True, first_air_date_year=None):
        return _FakeSearchResponse(self._tv_results)

    def movie(self, movie_id):
        return self._movie_details.get(movie_id, SimpleNamespace(alternative_titles=[]))

    def tv_show(self, tv_id):
        return self._tv_details.get(tv_id, SimpleNamespace(alternative_titles=[]))


class TMDBMovieMatchingServiceTests(SimpleTestCase):
    def test_normalize_title(self):
        normalized = TMDBMovieMatchingService.normalize_title("  Ёлки, 2!!!  ")
        self.assertEqual(normalized, "елки 2")

    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_exact_match_outscores_partial(self, get_tmdb_client_mock):
        movie = Movie(
            title="Матрица",
            original_title="The Matrix",
            year=1999,
            movie_type=Movie.MovieType.MOVIE,
        )
        candidate_exact = SimpleNamespace(
            id=1,
            title="Матрица",
            original_title="The Matrix",
            release_date=date(1999, 3, 31),
            poster_path="/m1.jpg",
            popularity=100.0,
            vote_average=8.7,
        )
        candidate_partial = SimpleNamespace(
            id=2,
            title="Матрица: Перезагрузка",
            original_title="The Matrix Reloaded",
            release_date=date(2003, 5, 15),
            poster_path="/m2.jpg",
            popularity=80.0,
            vote_average=7.2,
        )
        fake_tmdb = _FakeTMDB(
            movie_results=[candidate_exact, candidate_partial],
            movie_details={
                1: SimpleNamespace(alternative_titles=[]),
                2: SimpleNamespace(alternative_titles=[]),
            },
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        result = TMDBMovieMatchingService.match_movie(movie)

        self.assertEqual(result.status, "auto_match")
        self.assertIsNotNone(result.selected_candidate)
        self.assertEqual(result.selected_candidate.tmdb_id, 1)
        self.assertGreater(result.selected_candidate.score, 100)

    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_ambiguous_case_returns_candidates(self, get_tmdb_client_mock):
        movie = Movie(
            title="Дюна",
            original_title="",
            year=2021,
            movie_type=Movie.MovieType.MOVIE,
        )
        candidate_1 = SimpleNamespace(
            id=10,
            title="Дюна",
            original_title="Dune",
            release_date=date(2021, 9, 3),
            poster_path="/d1.jpg",
            popularity=90.0,
            vote_average=8.1,
        )
        candidate_2 = SimpleNamespace(
            id=11,
            title="Дюна",
            original_title="Dune",
            release_date=date(2021, 10, 1),
            poster_path="/d2.jpg",
            popularity=89.0,
            vote_average=8.0,
        )
        fake_tmdb = _FakeTMDB(
            movie_results=[candidate_1, candidate_2],
            movie_details={
                10: SimpleNamespace(alternative_titles=[]),
                11: SimpleNamespace(alternative_titles=[]),
            },
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        result = TMDBMovieMatchingService.match_movie(movie)

        self.assertEqual(result.status, "needs_user_choice")
        self.assertIsNone(result.selected_candidate)
        self.assertGreaterEqual(len(result.candidates), 2)
        ids = {c.tmdb_id for c in result.candidates}
        self.assertIn(10, ids)
        self.assertIn(11, ids)
