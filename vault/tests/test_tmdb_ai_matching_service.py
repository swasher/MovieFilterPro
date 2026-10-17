from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from core.models import Country
from vault.models import Movie, MoviePerson, Person
from vault.services.tmdb_ai_matching_service import AICastComparison, TMDBAIMatchingService
from vault.services.tmdb_match_resolver import TMDBMatchResolver


class CompareCastsTests(SimpleTestCase):
    def test_short_local_cast_returns_none_without_llm(self):
        with patch.object(TMDBAIMatchingService, "_chat_json") as chat_mock:
            result = TMDBAIMatchingService.compare_casts(
                ["Актёр 1", "Актёр 2"],
                ["Actor A", "Actor B", "Actor C", "Actor D", "Actor E"],
            )

        self.assertIsNone(result)
        chat_mock.assert_not_called()

    def test_short_candidate_cast_returns_none_without_llm(self):
        with patch.object(TMDBAIMatchingService, "_chat_json") as chat_mock:
            result = TMDBAIMatchingService.compare_casts(
                ["Актёр 1", "Актёр 2", "Актёр 3"],
                ["Actor A", "Actor B"],
            )

        self.assertIsNone(result)
        chat_mock.assert_not_called()

    def test_parses_json_verdict(self):
        response = {
            "overlap": 2,
            "matched_pairs": [
                "Киану Ривз — Keanu Reeves",
                "Лоренс Фишберн — Laurence Fishburne",
            ],
            "confidence": 0.9,
            "reason": "Двое ведущих актёров совпадают.",
        }
        with patch.object(TMDBAIMatchingService, "_chat_json", return_value=response):
            result = TMDBAIMatchingService.compare_casts(
                ["Киану Ривз", "Лоренс Фишберн", "Кэрри-Энн Мосс"],
                [
                    "Keanu Reeves",
                    "Laurence Fishburne",
                    "Joe Pantoliano",
                    "Hugo Weaving",
                    "Gloria Foster",
                ],
            )

        self.assertIsNotNone(result)
        self.assertEqual(result.overlap, 2)
        self.assertEqual(len(result.matched_pairs), 2)
        self.assertEqual(result.confidence, 0.9)

    def test_ai_unavailable_returns_none(self):
        with patch.object(TMDBAIMatchingService, "_chat_json", return_value=None):
            result = TMDBAIMatchingService.compare_casts(
                ["Actor A", "Actor B", "Actor C"],
                ["Actor A", "Actor B", "Actor C", "Actor D", "Actor E"],
            )

        self.assertIsNone(result)

    def test_clips_lists_to_ten_names(self):
        local = [f"Актёр {i}" for i in range(1, 16)]
        remote = [f"Actor {i}" for i in range(1, 16)]
        captured = {}

        def fake_chat(*, system_prompt, user_prompt):
            captured["user_prompt"] = user_prompt
            return {"overlap": 0, "matched_pairs": [], "confidence": 0.0, "reason": ""}

        with patch.object(TMDBAIMatchingService, "_chat_json", side_effect=fake_chat):
            TMDBAIMatchingService.compare_casts(local, remote)

        self.assertIn("Актёр 10", captured["user_prompt"])
        self.assertNotIn("Актёр 11", captured["user_prompt"])
        self.assertIn("Actor 10", captured["user_prompt"])
        self.assertNotIn("Actor 11", captured["user_prompt"])

    def test_bad_overlap_value_is_clamped_to_zero(self):
        with patch.object(
            TMDBAIMatchingService,
            "_chat_json",
            return_value={"overlap": -5, "matched_pairs": [], "confidence": 1.5, "reason": ""},
        ):
            result = TMDBAIMatchingService.compare_casts(
                ["A", "B", "C"],
                ["A", "B", "C", "D", "E"],
            )

        self.assertIsInstance(result, AICastComparison)
        self.assertEqual(result.overlap, 0)


class LocalActorNamesTests(TestCase):
    def _person(self, tmdb_id, imdb_id, name):
        country = Country.objects.get_or_create(name="Unknown", defaults={"code": "XX"})[0]
        return Person.objects.create(
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
            name=name,
            original_name=name,
            country=country,
        )

    def test_returns_top_actor_names_by_order(self):
        movie = Movie.objects.create(
            title="Т",
            original_title="",
            year=1999,
            movie_type=Movie.MovieType.MOVIE,
            status=Movie.Status.RELEASED,
        )
        for i in range(1, 4):
            person = self._person(f"100{i}", f"nm00{i}", f"Актёр {i}")
            MoviePerson.objects.create(
                movie=movie,
                person=person,
                role="actor",
                order=i,
                popularity=float(4 - i),
            )
        director = self._person("2000", "nm0099", "Режиссёр")
        MoviePerson.objects.create(movie=movie, person=director, role="director", order=0)

        names = TMDBMatchResolver._local_actor_names(movie)

        self.assertEqual(names, ["Актёр 1", "Актёр 2", "Актёр 3"])

    def test_unsaved_movie_returns_empty(self):
        movie = Movie(title="Т", original_title="", year=1999, movie_type=Movie.MovieType.MOVIE)

        self.assertEqual(TMDBMatchResolver._local_actor_names(movie), [])