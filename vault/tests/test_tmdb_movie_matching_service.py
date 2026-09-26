from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from vault.models import Movie
from vault.services.tmdb_ai_matching_service import AICandidateChoice, AIPlotComparison
from vault.services.tmdb_groq_matching_service import GroqChoice
from vault.services.tmdb_movie_matching_service import TMDBMovieMatchingService


class _FakeSearchResponse:
    def __init__(self, results):
        self.results = results


class _FakeTMDB:
    def __init__(self, movie_results=None, tv_results=None, movie_details=None, tv_details=None, find_results=None):
        self._movie_results = movie_results or []
        self._tv_results = tv_results or []
        self._movie_details = movie_details or {}
        self._tv_details = tv_details or {}
        self._find_results = find_results or SimpleNamespace(movie_results=[], tv_results=[])

    def movie_search(self, query, include_adult=True, primary_release_year=None):
        return _FakeSearchResponse(self._movie_results)

    def tv_search(self, query, include_adult=True, first_air_date_year=None):
        return _FakeSearchResponse(self._tv_results)

    def movie(self, movie_id):
        return self._movie_details.get(movie_id, SimpleNamespace(alternative_titles=[]))

    def tv_show(self, tv_id):
        return self._tv_details.get(tv_id, SimpleNamespace(alternative_titles=[]))

    def find_by_id(self, imdb_id=None, **kwargs):
        return self._find_results


class TMDBMovieMatchingServiceTests(SimpleTestCase):
    def test_normalize_title(self):
        normalized = TMDBMovieMatchingService.normalize_title("  Ёлки, 2!!!  ")
        self.assertEqual(normalized, "елки 2")

    def test_normalize_title_strips_edition_suffix(self):
        self.assertEqual(
            TMDBMovieMatchingService.normalize_title("Captain America: Brave New World (IMAX)"),
            "captain america brave new world",
        )
        self.assertEqual(
            TMDBMovieMatchingService.normalize_title("Носферату (Расширенная версия)"),
            "носферату",
        )
        # Скобки без маркеров изданий не трогаем.
        self.assertEqual(
            TMDBMovieMatchingService.normalize_title("Обычный фильм (2024)"),
            "обычный фильм 2024",
        )

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
            overview="Пол и Атрейдесы летят на Арракис.",
        )
        candidate_2 = SimpleNamespace(
            id=11,
            title="Дюна",
            original_title="Dune",
            release_date=date(2021, 10, 1),
            poster_path="/d2.jpg",
            popularity=89.0,
            vote_average=8.0,
            overview="Другая версия про пустынную планету.",
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
        by_id = {c.tmdb_id: c for c in result.candidates}
        self.assertEqual(by_id[10].overview, "Пол и Атрейдесы летят на Арракис.")
        self.assertEqual(by_id[11].overview, "Другая версия про пустынную планету.")

    @patch(
        "vault.services.tmdb_groq_matching_service.TMDBGROQMatchingService.choose_confident",
        return_value=None,
    )
    @patch(
        "vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.compare_plots",
        return_value=AIPlotComparison(same_work=True, confidence=0.92, reason="Сюжеты про Арракис совпадают."),
    )
    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.choose_best_candidate")
    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_ambiguous_case_can_auto_match_with_confident_ai_choice(
        self, get_tmdb_client_mock, choose_best_mock, compare_mock, groq_mock
    ):
        movie = Movie(
            title="Дюна",
            original_title="",
            year=2021,
            movie_type=Movie.MovieType.MOVIE,
            description="Наследник великого дома оказывается на пустынной планете Арракис, где добывают ценную пряность.",
        )
        candidate_1 = SimpleNamespace(
            id=10,
            title="Дюна",
            original_title="Dune",
            release_date=date(2021, 9, 3),
            poster_path="/d1.jpg",
            popularity=90.0,
            vote_average=8.1,
            overview="",
        )
        candidate_2 = SimpleNamespace(
            id=11,
            title="Дюна",
            original_title="Dune",
            release_date=date(2021, 10, 1),
            poster_path="/d2.jpg",
            popularity=89.0,
            vote_average=8.0,
            overview="Другая версия про пустынную планету.",
        )
        fake_tmdb = _FakeTMDB(
            movie_results=[candidate_1, candidate_2],
            movie_details={
                10: SimpleNamespace(
                    alternative_titles=[],
                    overview="Наследник дома Атрейдесов прибывает на Арракис и сталкивается с борьбой за контроль над пряностью.",
                ),
                11: SimpleNamespace(alternative_titles=[]),
            },
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        def choose_best(movie_arg, candidates):
            by_id = {candidate.tmdb_id: candidate for candidate in candidates}
            self.assertIn("Атрейдесов", by_id[10].overview)
            return AICandidateChoice(
                selected_candidate=by_id[10],
                confidence=0.96,
                runner_up_confidence=0.40,
                reason="Оба описания про наследника Атрейдесов на Арракисе и борьбу за пряность.",
                needs_human=False,
            )

        choose_best_mock.side_effect = choose_best

        result = TMDBMovieMatchingService.match_movie(movie)

        self.assertEqual(result.status, "auto_match")
        self.assertIsNotNone(result.selected_candidate)
        self.assertEqual(result.selected_candidate.tmdb_id, 10)
        self.assertIn("ai_plot_match", result.selected_candidate.score_reasons)
        self.assertIn("ai_plot_verified", result.selected_candidate.score_reasons)
        self.assertTrue(compare_mock.called)

    @patch(
        "vault.services.tmdb_groq_matching_service.TMDBGROQMatchingService.choose_confident",
        return_value=None,
    )
    @patch(
        "vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.compare_plots",
        return_value=AIPlotComparison(same_work=True, confidence=0.81, reason="Сюжеты совместимы."),
    )
    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.choose_best_candidate")
    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_ai_choice_can_break_tie_when_deterministic_best_is_strong(
        self, get_tmdb_client_mock, choose_best_mock, compare_mock, groq_mock
    ):
        movie = Movie(
            title="Взрывные триггер счастье",
            original_title="Trigger Happy",
            year=2025,
            movie_type=Movie.MovieType.MOVIE,
            description=(
                "Джордж Декер мечтает сбежать от своей жизни и полететь на Багамы, "
                "но чтобы попасть туда, ему придется найти способ сбежать от жены, долгов и унизительной работы."
            ),
        )
        candidate_1 = SimpleNamespace(
            id=1234422,
            title="Триггер счастье",
            original_title="Trigger Happy",
            release_date=date(2025, 1, 1),
            poster_path="/trigger.jpg",
            popularity=12.0,
            vote_average=6.0,
            overview="Подавленный муж пытается убить свою кормильцу жену ради ее полиса страхования жизни.",
        )
        candidate_2 = SimpleNamespace(
            id=1734125,
            title="Trigger Happy",
            original_title="Trigger Happy",
            release_date=date(2026, 1, 1),
            poster_path="/laser.jpg",
            popularity=10.0,
            vote_average=6.0,
            overview="Influencers fight to the death at a live-streamed, lethal laser-tag match.",
        )
        fake_tmdb = _FakeTMDB(
            movie_results=[candidate_1, candidate_2],
            movie_details={
                1234422: SimpleNamespace(alternative_titles=[]),
                1734125: SimpleNamespace(alternative_titles=[]),
            },
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        def choose_best(movie_arg, candidates):
            by_id = {candidate.tmdb_id: candidate for candidate in candidates}
            self.assertEqual(by_id[1234422].score, 90)
            self.assertEqual(by_id[1734125].score, 80)
            return AICandidateChoice(
                selected_candidate=by_id[1234422],
                confidence=0.74,
                runner_up_confidence=0.30,
                reason="Первый кандидат совпадает по названию и году, второй сюжетно про другое.",
                needs_human=True,
            )

        choose_best_mock.side_effect = choose_best

        result = TMDBMovieMatchingService.match_movie(movie)

        self.assertEqual(result.status, "auto_match")
        self.assertIsNotNone(result.selected_candidate)
        self.assertEqual(result.selected_candidate.tmdb_id, 1234422)
        self.assertIn("ai_plot_match", result.selected_candidate.score_reasons)
        self.assertIn("ai_plot_verified", result.selected_candidate.score_reasons)

    @patch(
        "vault.services.tmdb_groq_matching_service.TMDBGROQMatchingService.choose_confident",
        return_value=None,
    )
    @patch(
        "vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.compare_plots",
        return_value=AIPlotComparison(same_work=False, confidence=0.85, reason="Сюжеты про разное."),
    )
    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.choose_best_candidate")
    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_ai_choice_blocked_when_verify_rejects_winner(
        self, get_tmdb_client_mock, choose_best_mock, compare_mock, groq_mock
    ):
        movie = Movie(
            title="Дюна",
            original_title="",
            year=2021,
            movie_type=Movie.MovieType.MOVIE,
            description="Наследник великого дома оказывается на пустынной планете Арракис, где добывают ценную пряность.",
        )
        candidate_1 = SimpleNamespace(
            id=10,
            title="Дюна",
            original_title="Dune",
            release_date=date(2021, 9, 3),
            poster_path="/d1.jpg",
            popularity=90.0,
            vote_average=8.1,
            overview="Наследник дома Атрейдесов прибывает на Арракис и сталкивается с борьбой за контроль над пряностью.",
        )
        candidate_2 = SimpleNamespace(
            id=11,
            title="Дюна",
            original_title="Dune",
            release_date=date(2021, 10, 1),
            poster_path="/d2.jpg",
            popularity=89.0,
            vote_average=8.0,
            overview="Другая версия про пустынную планету.",
        )
        fake_tmdb = _FakeTMDB(
            movie_results=[candidate_1, candidate_2],
            movie_details={
                10: SimpleNamespace(alternative_titles=[]),
                11: SimpleNamespace(alternative_titles=[]),
            },
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        def choose_best(movie_arg, candidates):
            by_id = {candidate.tmdb_id: candidate for candidate in candidates}
            return AICandidateChoice(
                selected_candidate=by_id[10],
                confidence=0.96,
                runner_up_confidence=0.40,
                reason="Выбираю первого.",
                needs_human=False,
            )

        choose_best_mock.side_effect = choose_best

        result = TMDBMovieMatchingService.match_movie(movie)

        # Шаг 1 прошел, шаг 2 (попарная проверка) отклонил — остаемся в ручном режиме.
        self.assertEqual(result.status, "needs_user_choice")
        self.assertIsNone(result.selected_candidate)

    @patch(
        "vault.services.tmdb_groq_matching_service.TMDBGROQMatchingService.choose_confident",
        return_value=None,
    )
    @patch(
        "vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.compare_plots",
        return_value=None,
    )
    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.choose_best_candidate")
    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_ai_choice_blocked_when_verify_unavailable(
        self, get_tmdb_client_mock, choose_best_mock, compare_mock, groq_mock
    ):
        movie = Movie(
            title="Дюна",
            original_title="",
            year=2021,
            movie_type=Movie.MovieType.MOVIE,
            description="Наследник великого дома оказывается на пустынной планете Арракис, где добывают ценную пряность.",
        )
        candidate_1 = SimpleNamespace(
            id=10,
            title="Дюна",
            original_title="Dune",
            release_date=date(2021, 9, 3),
            poster_path="/d1.jpg",
            popularity=90.0,
            vote_average=8.1,
            overview="Наследник дома Атрейдесов прибывает на Арракис и сталкивается с борьбой за контроль над пряностью.",
        )
        candidate_2 = SimpleNamespace(
            id=11,
            title="Дюна",
            original_title="Dune",
            release_date=date(2021, 10, 1),
            poster_path="/d2.jpg",
            popularity=89.0,
            vote_average=8.0,
            overview="Другая версия про пустынную планету.",
        )
        fake_tmdb = _FakeTMDB(
            movie_results=[candidate_1, candidate_2],
            movie_details={
                10: SimpleNamespace(alternative_titles=[]),
                11: SimpleNamespace(alternative_titles=[]),
            },
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        def choose_best(movie_arg, candidates):
            by_id = {candidate.tmdb_id: candidate for candidate in candidates}
            return AICandidateChoice(
                selected_candidate=by_id[10],
                confidence=0.96,
                runner_up_confidence=0.40,
                reason="Выбираю первого.",
                needs_human=False,
            )

        choose_best_mock.side_effect = choose_best

        result = TMDBMovieMatchingService.match_movie(movie)

        # Второй запрос упал — консервативно не делаем автомата.
        self.assertEqual(result.status, "needs_user_choice")
        self.assertIsNone(result.selected_candidate)

    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_find_by_imdb_id_returns_auto_match_for_single_movie_result(self, get_tmdb_client_mock):
        fake_tmdb = _FakeTMDB(
            find_results=SimpleNamespace(
                movie_results=[
                    SimpleNamespace(
                        id=321,
                        title="Интерстеллар",
                        original_title="Interstellar",
                        release_date=date(2014, 11, 7),
                        poster_path="/poster.jpg",
                        popularity=99.0,
                        vote_average=8.7,
                    )
                ],
                tv_results=[],
            )
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        result = TMDBMovieMatchingService.find_by_imdb_id("tt0816692", expected_media_type="movie")

        self.assertEqual(result.status, "auto_match")
        self.assertIsNotNone(result.selected_candidate)
        self.assertEqual(result.selected_candidate.tmdb_id, 321)
        self.assertEqual(result.selected_candidate.media_type, "movie")

    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_singleton_title_year_exact_auto_matches_despite_dirty_original(self, get_tmdb_client_mock):
        # Кейс из prod-очереди: Kinorium хранит английский международный тайтл,
        # TMDB — настоящий оригинал. RU-название и год точные, кандидат один.
        movie = Movie(
            title="Женщина в очереди",
            original_title="The Woman in the Line",
            year=2025,
            movie_type=Movie.MovieType.MOVIE,
        )
        candidate = SimpleNamespace(
            id=1193861,
            title="Женщина в очереди",
            original_title="La mujer de la fila",
            release_date=date(2025, 1, 1),
            poster_path="/w.jpg",
            popularity=10.0,
            vote_average=7.0,
        )
        fake_tmdb = _FakeTMDB(
            movie_results=[candidate],
            movie_details={1193861: SimpleNamespace(alternative_titles=[])},
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        result = TMDBMovieMatchingService.match_movie(movie)

        self.assertEqual(result.status, "auto_match")
        self.assertIsNotNone(result.selected_candidate)
        self.assertEqual(result.selected_candidate.tmdb_id, 1193861)
        self.assertIn("title_exact", result.selected_candidate.score_reasons)
        self.assertIn("year_exact", result.selected_candidate.score_reasons)

    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_singleton_year_near_stays_confirmation(self, get_tmdb_client_mock):
        movie = Movie(
            title="Перегонщик",
            original_title="",
            year=2025,
            movie_type=Movie.MovieType.MOVIE,
        )
        candidate = SimpleNamespace(
            id=1591602,
            title="Перегонщик",
            original_title="Перегонщик",
            release_date=date(2024, 1, 1),
            poster_path="/p.jpg",
            popularity=5.0,
            vote_average=6.0,
        )
        fake_tmdb = _FakeTMDB(
            movie_results=[candidate],
            movie_details={1591602: SimpleNamespace(alternative_titles=[])},
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        result = TMDBMovieMatchingService.match_movie(movie)

        self.assertEqual(result.status, "needs_confirmation")

    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_singleton_alternative_title_only_stays_confirmation(self, get_tmdb_client_mock):
        movie = Movie(
            title="Токсик",
            original_title="Akiplesa",
            year=2024,
            movie_type=Movie.MovieType.MOVIE,
        )
        candidate = SimpleNamespace(
            id=1315091,
            title="Токсичность",
            original_title="Akiplėša",
            release_date=date(2024, 1, 1),
            poster_path="/t.jpg",
            popularity=5.0,
            vote_average=6.0,
        )
        fake_tmdb = _FakeTMDB(
            movie_results=[candidate],
            movie_details={
                1315091: SimpleNamespace(
                    alternative_titles=[SimpleNamespace(title="Токсик")]
                ),
            },
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        result = TMDBMovieMatchingService.match_movie(movie)

        self.assertEqual(result.status, "needs_confirmation")

    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.compare_plots")
    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.choose_best_candidate")
    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_literal_plot_match_short_circuits_ai_for_singleton(
        self, get_tmdb_client_mock, choose_best_mock, compare_mock
    ):
        plot = (
            "Наследник великого дома оказывается на пустынной планете Арракис, "
            "где добывают ценную пряность, и возглавляет восстание фременов против империи."
        )
        movie = Movie(
            title="Перегонщик",
            original_title="",
            year=2025,
            movie_type=Movie.MovieType.MOVIE,
            description=plot,
        )
        candidate = SimpleNamespace(
            id=1591602,
            title="Перегонщик",
            original_title="Перегонщик",
            release_date=date(2024, 1, 1),
            poster_path="/p.jpg",
            popularity=5.0,
            vote_average=6.0,
            overview=plot,
        )
        fake_tmdb = _FakeTMDB(
            movie_results=[candidate],
            movie_details={1591602: SimpleNamespace(alternative_titles=[])},
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        result = TMDBMovieMatchingService.match_movie(movie)

        self.assertEqual(result.status, "auto_match")
        self.assertIsNotNone(result.selected_candidate)
        self.assertEqual(result.selected_candidate.tmdb_id, 1591602)
        self.assertIn("plot_literal_match", result.selected_candidate.score_reasons)
        self.assertNotIn("ai_plot_match", result.selected_candidate.score_reasons)
        choose_best_mock.assert_not_called()
        compare_mock.assert_not_called()

    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.compare_plots")
    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.choose_best_candidate")
    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_literal_plot_match_picks_one_of_several_without_ai(
        self, get_tmdb_client_mock, choose_best_mock, compare_mock
    ):
        plot_a = (
            "Наследник великого дома оказывается на пустынной планете Арракис, "
            "где добывают ценную пряность, и возглавляет восстание фременов против империи."
        )
        plot_b = (
            "Influencers fight to the death at a live-streamed lethal laser-tag match "
            "on an abandoned island resort far from civilization."
        )
        movie = Movie(
            title="Дюна",
            original_title="",
            year=2021,
            movie_type=Movie.MovieType.MOVIE,
            description=plot_a,
        )
        candidate_1 = SimpleNamespace(
            id=10,
            title="Дюна",
            original_title="Dune",
            release_date=date(2021, 9, 3),
            poster_path="/d1.jpg",
            popularity=90.0,
            vote_average=8.1,
            overview=plot_a,
        )
        candidate_2 = SimpleNamespace(
            id=11,
            title="Дюна",
            original_title="Dune",
            release_date=date(2021, 10, 1),
            poster_path="/d2.jpg",
            popularity=89.0,
            vote_average=8.0,
            overview=plot_b,
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

        self.assertEqual(result.status, "auto_match")
        self.assertIsNotNone(result.selected_candidate)
        self.assertEqual(result.selected_candidate.tmdb_id, 10)
        self.assertIn("plot_literal_match", result.selected_candidate.score_reasons)
        choose_best_mock.assert_not_called()
        compare_mock.assert_not_called()

    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.compare_plots")
    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.choose_best_candidate")
    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_literal_plot_match_ignores_case_and_punctuation(
        self, get_tmdb_client_mock, choose_best_mock, compare_mock
    ):
        overview = (
            "Наследник великого дома оказывается на пустынной планете Арракис, "
            "где добывают ценную пряность, и возглавляет восстание фременов против империи."
        )
        movie = Movie(
            title="Перегонщик",
            original_title="",
            year=2025,
            movie_type=Movie.MovieType.MOVIE,
            description="НАСЛЕДНИК Великого Дома!!! оказывается на пустынной планете Арракис, "
            "где добывают ценную пряность — и возглавляет восстание фременов против империи...",
        )
        candidate = SimpleNamespace(
            id=1591602,
            title="Перегонщик",
            original_title="Перегонщик",
            release_date=date(2024, 1, 1),
            poster_path="/p.jpg",
            popularity=5.0,
            vote_average=6.0,
            overview=overview,
        )
        fake_tmdb = _FakeTMDB(
            movie_results=[candidate],
            movie_details={1591602: SimpleNamespace(alternative_titles=[])},
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        result = TMDBMovieMatchingService.match_movie(movie)

        self.assertEqual(result.status, "auto_match")
        self.assertIsNotNone(result.selected_candidate)
        self.assertEqual(result.selected_candidate.tmdb_id, 1591602)
        self.assertIn("plot_literal_match", result.selected_candidate.score_reasons)
        choose_best_mock.assert_not_called()
        compare_mock.assert_not_called()

    @patch(
        "vault.services.tmdb_groq_matching_service.TMDBGROQMatchingService.choose_confident",
        return_value=None,
    )
    @patch(
        "vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.compare_plots",
        return_value=AIPlotComparison(same_work=True, confidence=0.9, reason="Сюжеты совпадают."),
    )
    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.choose_best_candidate")
    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_two_literal_hits_fall_through_to_ai(
        self, get_tmdb_client_mock, choose_best_mock, compare_mock, groq_mock
    ):
        plot = (
            "Наследник великого дома оказывается на пустынной планете Арракис, "
            "где добывают ценную пряность, и возглавляет восстание фременов против империи."
        )
        movie = Movie(
            title="Дюна",
            original_title="",
            year=2021,
            movie_type=Movie.MovieType.MOVIE,
            description=plot,
        )
        candidate_1 = SimpleNamespace(
            id=10,
            title="Дюна",
            original_title="Dune",
            release_date=date(2021, 9, 3),
            poster_path="/d1.jpg",
            popularity=90.0,
            vote_average=8.1,
            overview=plot,
        )
        candidate_2 = SimpleNamespace(
            id=11,
            title="Дюна",
            original_title="Dune",
            release_date=date(2021, 10, 1),
            poster_path="/d2.jpg",
            popularity=89.0,
            vote_average=8.0,
            overview=plot,
        )
        fake_tmdb = _FakeTMDB(
            movie_results=[candidate_1, candidate_2],
            movie_details={
                10: SimpleNamespace(alternative_titles=[]),
                11: SimpleNamespace(alternative_titles=[]),
            },
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        def choose_best(movie_arg, candidates):
            by_id = {candidate.tmdb_id: candidate for candidate in candidates}
            return AICandidateChoice(
                selected_candidate=by_id[10],
                confidence=0.96,
                runner_up_confidence=0.40,
                reason="Выбираю первого.",
                needs_human=False,
            )

        choose_best_mock.side_effect = choose_best

        result = TMDBMovieMatchingService.match_movie(movie)

        # Два дословных попадания — неоднозначность, решает AI.
        self.assertEqual(result.status, "auto_match")
        self.assertIsNotNone(result.selected_candidate)
        self.assertEqual(result.selected_candidate.tmdb_id, 10)
        self.assertIn("ai_plot_match", result.selected_candidate.score_reasons)
        self.assertNotIn("plot_literal_match", result.selected_candidate.score_reasons)

    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.compare_plots")
    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.choose_best_candidate")
    @patch("vault.services.tmdb_groq_matching_service.TMDBGROQMatchingService.choose_confident")
    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_groq_confident_match_skips_local_ai(
        self, get_tmdb_client_mock, groq_mock, choose_best_mock, compare_mock
    ):
        movie = Movie(
            title="Взрывные триггер счастье",
            original_title="Trigger Happy",
            year=2025,
            movie_type=Movie.MovieType.MOVIE,
            description=(
                "Джордж Декер мечтает сбежать от своей жизни и полететь на Багамы, "
                "но чтобы попасть туда, ему придется найти способ сбежать от жены, долгов и унизительной работы."
            ),
        )
        candidate_1 = SimpleNamespace(
            id=1234422,
            title="Триггер счастье",
            original_title="Trigger Happy",
            release_date=date(2025, 1, 1),
            poster_path="/trigger.jpg",
            popularity=12.0,
            vote_average=6.0,
            overview="Подавленный муж пытается убить свою кормильцу жену ради ее полиса страхования жизни.",
        )
        candidate_2 = SimpleNamespace(
            id=1734125,
            title="Trigger Happy",
            original_title="Trigger Happy",
            release_date=date(2026, 1, 1),
            poster_path="/laser.jpg",
            popularity=10.0,
            vote_average=6.0,
            overview="Influencers fight to the death at a live-streamed, lethal laser-tag match.",
        )
        fake_tmdb = _FakeTMDB(
            movie_results=[candidate_1, candidate_2],
            movie_details={
                1234422: SimpleNamespace(alternative_titles=[]),
                1734125: SimpleNamespace(alternative_titles=[]),
            },
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        def choose_confident(movie_arg, candidates):
            by_id = {candidate.tmdb_id: candidate for candidate in candidates}
            return GroqChoice(
                selected_candidate=by_id[1234422],
                confidence=0.92,
                runner_up_confidence=0.30,
                reason="Совпали Джордж Декер, Багамы и долги.",
            )

        groq_mock.side_effect = choose_confident

        result = TMDBMovieMatchingService.match_movie(movie)

        self.assertEqual(result.status, "auto_match")
        self.assertIsNotNone(result.selected_candidate)
        self.assertEqual(result.selected_candidate.tmdb_id, 1234422)
        self.assertIn("groq_plot_match", result.selected_candidate.score_reasons)
        self.assertNotIn("ai_plot_match", result.selected_candidate.score_reasons)
        choose_best_mock.assert_not_called()
        compare_mock.assert_not_called()

    @patch(
        "vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.compare_plots",
        return_value=AIPlotComparison(same_work=True, confidence=0.9, reason="Сюжеты совпадают."),
    )
    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.choose_best_candidate")
    @patch("vault.services.tmdb_groq_matching_service.TMDBGROQMatchingService.choose_confident")
    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_unsure_groq_falls_through_to_local_ai(
        self, get_tmdb_client_mock, groq_mock, choose_best_mock, compare_mock
    ):
        movie = Movie(
            title="Взрывные триггер счастье",
            original_title="Trigger Happy",
            year=2025,
            movie_type=Movie.MovieType.MOVIE,
            description=(
                "Джордж Декер мечтает сбежать от своей жизни и полететь на Багамы, "
                "но чтобы попасть туда, ему придется найти способ сбежать от жены, долгов и унизительной работы."
            ),
        )
        candidate_1 = SimpleNamespace(
            id=1234422,
            title="Триггер счастье",
            original_title="Trigger Happy",
            release_date=date(2025, 1, 1),
            poster_path="/trigger.jpg",
            popularity=12.0,
            vote_average=6.0,
            overview="Подавленный муж пытается убить свою кормильцу жену ради ее полиса страхования жизни.",
        )
        candidate_2 = SimpleNamespace(
            id=1734125,
            title="Trigger Happy",
            original_title="Trigger Happy",
            release_date=date(2026, 1, 1),
            poster_path="/laser.jpg",
            popularity=10.0,
            vote_average=6.0,
            overview="Influencers fight to the death at a live-streamed, lethal laser-tag match.",
        )
        fake_tmdb = _FakeTMDB(
            movie_results=[candidate_1, candidate_2],
            movie_details={
                1234422: SimpleNamespace(alternative_titles=[]),
                1734125: SimpleNamespace(alternative_titles=[]),
            },
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        def choose_confident(movie_arg, candidates):
            by_id = {candidate.tmdb_id: candidate for candidate in candidates}
            return GroqChoice(
                selected_candidate=by_id[1234422],
                confidence=0.60,
                runner_up_confidence=0.55,
                reason="Похоже, но без уникальных имен.",
            )

        def choose_best(movie_arg, candidates):
            by_id = {candidate.tmdb_id: candidate for candidate in candidates}
            return AICandidateChoice(
                selected_candidate=by_id[1234422],
                confidence=0.96,
                runner_up_confidence=0.40,
                reason="Локальный AI подтверждает.",
                needs_human=False,
            )

        groq_mock.side_effect = choose_confident
        choose_best_mock.side_effect = choose_best

        result = TMDBMovieMatchingService.match_movie(movie)

        # GROQ не уверен — решает локальный AI.
        self.assertEqual(result.status, "auto_match")
        self.assertIsNotNone(result.selected_candidate)
        self.assertEqual(result.selected_candidate.tmdb_id, 1234422)
        self.assertIn("ai_plot_match", result.selected_candidate.score_reasons)
        self.assertNotIn("groq_plot_match", result.selected_candidate.score_reasons)

    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.compare_plots")
    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.choose_best_candidate")
    @patch("vault.services.tmdb_groq_matching_service.TMDBGROQMatchingService.choose_confident")
    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_groq_trope_level_match_without_names_auto_matches(
        self, get_tmdb_client_mock, groq_mock, choose_best_mock, compare_mock
    ):
        movie = Movie(
            title="Взрывные триггер счастье",
            original_title="Trigger Happy",
            year=2025,
            movie_type=Movie.MovieType.MOVIE,
            description=(
                "Джордж Декер мечтает сбежать от своей жизни и полететь на Багамы, "
                "но чтобы попасть туда, ему придется найти способ сбежать от жены, долгов и унизительной работы."
            ),
        )
        candidate_1 = SimpleNamespace(
            id=1234422,
            title="Триггер счастье",
            original_title="Trigger Happy",
            release_date=date(2025, 1, 1),
            poster_path="/trigger.jpg",
            popularity=12.0,
            vote_average=6.0,
            overview="Подавленный муж пытается убить свою кормильцу жену ради ее полиса страхования жизни.",
        )
        candidate_2 = SimpleNamespace(
            id=1734125,
            title="Trigger Happy",
            original_title="Trigger Happy",
            release_date=date(2026, 1, 1),
            poster_path="/laser.jpg",
            popularity=10.0,
            vote_average=6.0,
            overview="Influencers fight to the death at a live-streamed, lethal laser-tag match.",
        )
        fake_tmdb = _FakeTMDB(
            movie_results=[candidate_1, candidate_2],
            movie_details={
                1234422: SimpleNamespace(alternative_titles=[]),
                1734125: SimpleNamespace(alternative_titles=[]),
            },
        )
        get_tmdb_client_mock.return_value = fake_tmdb

        def choose_confident(movie_arg, candidates):
            by_id = {candidate.tmdb_id: candidate for candidate in candidates}
            return GroqChoice(
                selected_candidate=by_id[1234422],
                confidence=0.68,
                runner_up_confidence=0.30,
                reason="Имен нет, но совпали значимые тропы: побег от жены, долгов и работы.",
            )

        groq_mock.side_effect = choose_confident

        result = TMDBMovieMatchingService.match_movie(movie)

        self.assertEqual(result.status, "auto_match")
        self.assertIsNotNone(result.selected_candidate)
        self.assertEqual(result.selected_candidate.tmdb_id, 1234422)
        self.assertIn("groq_plot_match", result.selected_candidate.score_reasons)
        choose_best_mock.assert_not_called()
        compare_mock.assert_not_called()


class _YearFilterFakeTMDB:
    """Годовой фильтр убивает выдачу: с годом — пусто, без года — кандидат."""

    def __init__(self, candidate):
        self.candidate = candidate

    def movie_search(self, query, include_adult=True, primary_release_year=None):
        if primary_release_year is not None:
            return _FakeSearchResponse([])
        return _FakeSearchResponse([self.candidate] if self.candidate else [])

    def tv_search(self, query, include_adult=True, first_air_date_year=None):
        return _FakeSearchResponse([])

    def movie(self, movie_id):
        return SimpleNamespace(alternative_titles=[])

    def tv_show(self, tv_id):
        return SimpleNamespace(alternative_titles=[])


class SmartSearchFallbackTests(SimpleTestCase):
    plot = (
        "Тридцатилетний Азиз мечтает о кулинарном конкурсе, но странное завещание мамы "
        "ставит победу под угрозу, и ради неё он готов жениться на случайной попутчице Карине."
    )

    def _movie(self, **kwargs):
        params = {
            "title": "Про секс спроси у мамы",
            "original_title": "Ask Mom about Sex",
            "year": 2024,
            "movie_type": Movie.MovieType.MOVIE,
            "description": self.plot,
        }
        params.update(kwargs)
        return Movie(**params)

    def _candidate(self, overview=None, title="Про секс спроси у мамы"):
        return SimpleNamespace(
            id=1271103,
            title=title,
            original_title=title,
            release_date=date(2021, 1, 1),
            poster_path="/p.jpg",
            popularity=5.0,
            vote_average=6.0,
            overview=overview if overview is not None else self.plot,
        )

    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.compare_plots")
    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.choose_best_candidate")
    @patch("vault.services.tmdb_smart_search_service.is_local_ai_available", return_value=False)
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client_en")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client")
    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_empty_main_search_is_rescued_by_smart_literal(
        self, main_client_mock, smart_ru_mock, smart_en_mock, _ai_mock, choose_best_mock, compare_mock
    ):
        fake = _YearFilterFakeTMDB(self._candidate())
        main_client_mock.return_value = fake
        smart_ru_mock.return_value = fake
        smart_en_mock.return_value = fake

        result = TMDBMovieMatchingService.match_movie(self._movie())

        self.assertEqual(result.status, "auto_match")
        self.assertEqual(result.selected_candidate.tmdb_id, 1271103)
        self.assertIn("plot_literal_match", result.selected_candidate.score_reasons)
        choose_best_mock.assert_not_called()
        compare_mock.assert_not_called()

    @patch("vault.services.tmdb_smart_search_service.is_local_ai_available", return_value=False)
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client_en")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client")
    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_smart_finds_nothing_keeps_not_found(self, main_client_mock, smart_ru_mock, smart_en_mock, _ai_mock):
        fake = _YearFilterFakeTMDB(None)
        main_client_mock.return_value = fake
        smart_ru_mock.return_value = fake
        smart_en_mock.return_value = fake

        result = TMDBMovieMatchingService.match_movie(self._movie())

        self.assertEqual(result.status, "not_found")
        self.assertIsNone(result.selected_candidate)
        self.assertIn("Умный поиск", result.message)

    @patch("vault.services.tmdb_smart_search_service.smart_search", side_effect=RuntimeError("бум"))
    @patch("vault.services.tmdb_movie_matching_service.get_tmdb_client")
    def test_smart_exception_falls_back_to_original(self, main_client_mock, _smart_mock):
        main_client_mock.return_value = _YearFilterFakeTMDB(None)

        result = TMDBMovieMatchingService.match_movie(self._movie())

        self.assertEqual(result.status, "not_found")
        self.assertEqual(result.message, "Кандидаты TMDB не найдены")
