from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from vault.models import Movie
from vault.services.tmdb_ai_matching_service import AIPlotComparison
from vault.services.tmdb_smart_search_service import (
    SmartCandidate,
    coerce_year,
    collect_candidates,
    pick_winner,
    plots_match_literally,
    rank_candidates,
    release_year,
    smart_search,
    title_variants,
)


def _candidate(tmdb_id, title="", original_title="", year=None, alt_titles=()):
    return SmartCandidate(
        tmdb_id=tmdb_id,
        title=title,
        original_title=original_title,
        year=year,
        alt_titles=tuple(alt_titles),
    )


class SmartSearchHelpersTests(SimpleTestCase):
    def test_coerce_year(self):
        self.assertEqual(coerce_year(2024), 2024)
        self.assertEqual(coerce_year("2024"), 2024)
        self.assertEqual(coerce_year(" 2021 "), 2021)
        self.assertIsNone(coerce_year(None))
        self.assertIsNone(coerce_year(""))
        self.assertIsNone(coerce_year("не знаю"))

    def test_release_year(self):
        self.assertEqual(release_year("2021-01-01"), 2021)
        self.assertIsNone(release_year(""))
        self.assertIsNone(release_year(None))

    def test_title_variants_dedupes_and_drops_empty(self):
        candidate = _candidate(1, title="А", original_title="А", alt_titles=["B", "", "А"])
        self.assertEqual(title_variants(candidate), ["А", "B"])

    def test_rank_exact_match_first(self):
        candidates = [
            _candidate(1, title="Другой фильм", year=2020),
            _candidate(2, title="Про секс спроси у мамы", year=2021),
        ]
        ranked = rank_candidates(candidates, "Про секс спроси у мамы", 2024)
        self.assertEqual([c.tmdb_id for c, _, _ in ranked], [2, 1])
        self.assertEqual(ranked[0][1:], (3, 0))

    def test_rank_uses_english_alt_title(self):
        candidates = [_candidate(1, title="Про секс спроси у мамы", original_title="Про секс спроси у мамы", alt_titles=["Ask Mom About Sex"])]
        ranked = rank_candidates(candidates, "Ask Mom About Sex", None)
        self.assertEqual(ranked[0][1], 3)

    def test_rank_year_bonus(self):
        candidates = [
            _candidate(1, title="X", year=2020),
            _candidate(2, title="X", year=2024),
        ]
        ranked = rank_candidates(candidates, "Совсем другое", 2024)
        self.assertEqual([(c.tmdb_id, yb) for c, _, yb in ranked], [(2, 2), (1, 0)])

    def test_rank_stable_without_bonuses(self):
        candidates = [_candidate(1, title="A"), _candidate(2, title="B")]
        ranked = rank_candidates(candidates, "", None)
        self.assertEqual([c.tmdb_id for c, _, _ in ranked], [1, 2])

    def test_literal_equality_ignores_case_and_punctuation(self):
        plot = (
            "Наследник великого дома оказывается на пустынной планете Арракис, "
            "где добывают ценную пряность, и возглавляет восстание фременов против империи."
        )
        other = (
            "НАСЛЕДНИК Великого Дома!!! оказывается на пустынной планете Арракис, "
            "где добывают ценную пряность — и возглавляет восстание фременов против империи..."
        )
        self.assertTrue(plots_match_literally(plot, other))

    def test_literal_rejects_containment(self):
        plot = (
            "Наследник великого дома оказывается на пустынной планете Арракис, "
            "где добывают ценную пряность, и возглавляет восстание фременов против империи."
        )
        self.assertFalse(plots_match_literally(plot, plot + " А ещё у него была собака и дом."))
        self.assertFalse(plots_match_literally("коротко", "коротко"))
        self.assertFalse(
            plots_match_literally(plot, "Совсем другой сюжет про космос и далёкие галактики в опасности.")
        )


class _FakeLangClient:
    """Фейк TMDB-клиента с результатами на одном языке, пишет вызовы."""

    def __init__(self, results_by_query):
        self.results_by_query = results_by_query
        self.calls = []

    def movie_search(self, query, include_adult=True, **kwargs):
        self.calls.append(("movie", query, kwargs))
        return SimpleNamespace(results=list(self.results_by_query.get(query, [])))

    def tv_search(self, query, include_adult=True, **kwargs):
        self.calls.append(("tv", query, kwargs))
        return SimpleNamespace(results=[])


def _item(tmdb_id, title, original_title, overview, release_date="2021-01-01"):
    return SimpleNamespace(
        id=tmdb_id,
        title=title,
        original_title=original_title,
        overview=overview,
        release_date=release_date,
        poster_path="/p.jpg",
        popularity=5.0,
        vote_average=6.0,
    )


class SmartSearchCollectTests(SimpleTestCase):
    def test_merges_ru_and_en_variants(self):
        tmdb_ru = _FakeLangClient({"Ask": [_item(1, "Про секс", "Про секс", "", "2021-01-01")]})
        tmdb_en = _FakeLangClient({"Ask": [_item(1, "Ask Mom About Sex", "Ask Mom About Sex", "En overview")]})
        found = collect_candidates(tmdb_ru=tmdb_ru, tmdb_en=tmdb_en, queries=["Ask"], media_order=("movie",))
        self.assertEqual(len(found), 1)
        candidate = found[0]
        self.assertEqual(candidate.tmdb_id, 1)
        self.assertEqual(candidate.title, "Про секс")
        self.assertIn("Ask Mom About Sex", candidate.alt_titles)
        self.assertEqual(candidate.overview_en, "En overview")
        self.assertEqual(candidate.year, 2021)

    def test_search_is_year_free(self):
        tmdb_ru = _FakeLangClient({})
        tmdb_en = _FakeLangClient({})
        collect_candidates(tmdb_ru=tmdb_ru, tmdb_en=tmdb_en, queries=["X"], media_order=("movie", "tv"))
        for _, _, kwargs in tmdb_ru.calls + tmdb_en.calls:
            self.assertNotIn("primary_release_year", kwargs)
            self.assertNotIn("first_air_date_year", kwargs)

    def test_dedupes_across_queries_and_skips_idless(self):
        item = _item(7, "T", "T", "O")
        noid = SimpleNamespace(id=None, title="Ghost", overview="O")
        tmdb_ru = _FakeLangClient({"A": [item, noid], "B": [item]})
        tmdb_en = _FakeLangClient({})
        found = collect_candidates(tmdb_ru=tmdb_ru, tmdb_en=tmdb_en, queries=["A", "B", ""], media_order=("movie",))
        self.assertEqual([c.tmdb_id for c in found], [7])


def _smart_movie(**kwargs):
    params = {
        "title": "Про секс спроси у мамы",
        "original_title": "Ask Mom about Sex",
        "year": 2024,
        "movie_type": Movie.MovieType.MOVIE,
        "description": (
            "30-летний Азиз мечтает о кулинарном конкурсе, но странное завещание мамы "
            "ставит победу под угрозу, и ради неё он готов жениться на случайной попутчице Карине."
        ),
    }
    params.update(kwargs)
    return Movie(**params)


def _overview_item(tmdb_id, overview, title="Про секс спроси у мамы", release_date="2021-01-01"):
    return SimpleNamespace(
        id=tmdb_id, title=title, original_title=title, overview=overview,
        release_date=release_date, poster_path="/p.jpg", popularity=5.0, vote_average=6.0,
    )


class SmartSearchOrchestrationTests(SimpleTestCase):
    def setUp(self):
        # Tavily — внешний сервис: в orchestration-тестах по умолчанию пустой контекст.
        patcher = patch(
            "vault.services.tmdb_smart_search_service.TavilyService.search_web",
            return_value="",
        )
        self.search_web_mock = patcher.start()
        self.addCleanup(patcher.stop)

    def _clients(self, items):
        by_query = {"Ask Mom about Sex": items, "Про секс спроси у мамы": items}
        return _FakeLangClient(by_query), _FakeLangClient(by_query)

    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client_en")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client")
    @patch("vault.services.tmdb_smart_search_service.is_local_ai_available", return_value=False)
    def test_ai_unavailable_without_literal_is_not_found(self, _ai_mock, ru_mock, en_mock):
        ru_mock.return_value, en_mock.return_value = self._clients(
            [_overview_item(1, "Совершенно другой сюжет про космос и далёкие галактики в опасности.")]
        )
        result = smart_search(_smart_movie())
        self.assertEqual(result.status, "not_found")
        self.assertIn("AI", result.message)

    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client_en")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client")
    @patch("vault.services.tmdb_smart_search_service.is_local_ai_available", return_value=False)
    def test_ai_unavailable_with_single_literal_is_auto_match(self, _ai_mock, ru_mock, en_mock):
        movie = _smart_movie()
        ru_mock.return_value, en_mock.return_value = self._clients([_overview_item(1, movie.description)])
        result = smart_search(movie)
        self.assertEqual(result.status, "auto_match")
        self.assertEqual(result.selected_candidate.tmdb_id, 1)
        self.assertIn("plot_literal_match", result.selected_candidate.score_reasons)

    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.compare_plots")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client_en")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client")
    @patch("vault.services.tmdb_smart_search_service.is_local_ai_available", return_value=True)
    def test_plot_match_is_auto_match(self, _ai_mock, ru_mock, en_mock, compare_mock):
        compare_mock.return_value = AIPlotComparison(same_work=True, confidence=1.0, reason="Тот же фильм.")
        ru_mock.return_value, en_mock.return_value = self._clients(
            [_overview_item(1, "Азиз и Карина побеждают в кулинарном конкурсе вопреки завещанию мамы.")]
        )
        result = smart_search(_smart_movie())
        self.assertEqual(result.status, "auto_match")
        self.assertEqual(result.selected_candidate.tmdb_id, 1)
        self.assertIn("smart_search_plot_match", result.selected_candidate.score_reasons)
        self.assertEqual(result.selected_candidate.score, 100)

    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.compare_plots")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client_en")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client")
    @patch("vault.services.tmdb_smart_search_service.is_local_ai_available", return_value=True)
    def test_strict_threshold_rejects_four_on_year_mismatch(self, _ai_mock, ru_mock, en_mock, compare_mock):
        compare_mock.return_value = AIPlotComparison(same_work=True, confidence=0.8, reason="Похоже.")
        ru_mock.return_value, en_mock.return_value = self._clients(
            [_overview_item(1, "Азиз и Карина побеждают в кулинарном конкурсе вопреки завещанию мамы.")]
        )
        result = smart_search(_smart_movie(year=2024))
        self.assertEqual(result.status, "not_found")

    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.compare_plots")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client_en")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client")
    @patch("vault.services.tmdb_smart_search_service.is_local_ai_available", return_value=True)
    def test_confident_different_is_not_a_match(self, _ai_mock, ru_mock, en_mock, compare_mock):
        # Регрессия: confidence — уверенность в вердикте, а не похожесть.
        # same_work=False + confidence=1.0 означает «точно разные», а не скор 1.0.
        compare_mock.return_value = AIPlotComparison(
            same_work=False, confidence=1.0, reason="Разные жанры.", red_flags=("разные жанры",),
        )
        ru_mock.return_value, en_mock.return_value = self._clients(
            [_overview_item(1, "Анонс турнира по единоборствам KSW в Польше.")]
        )
        result = smart_search(_smart_movie())
        self.assertEqual(result.status, "not_found")
        self.assertIsNone(result.selected_candidate)

    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.compare_plots")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client_en")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client")
    @patch("vault.services.tmdb_smart_search_service.is_local_ai_available", return_value=True)
    def test_same_work_with_red_flags_is_not_a_match(self, _ai_mock, ru_mock, en_mock, compare_mock):
        compare_mock.return_value = AIPlotComparison(
            same_work=True, confidence=0.95, reason="Сомнительно.", red_flags=("сиквел?",),
        )
        ru_mock.return_value, en_mock.return_value = self._clients(
            [_overview_item(1, "Азиз и Карина побеждают в кулинарном конкурсе вопреки завещанию мамы.")]
        )
        result = smart_search(_smart_movie())
        self.assertEqual(result.status, "not_found")

    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client_en")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client")
    def test_no_candidates_is_not_found(self, ru_mock, en_mock):
        ru_mock.return_value, en_mock.return_value = _FakeLangClient({}), _FakeLangClient({})
        result = smart_search(_smart_movie())
        self.assertEqual(result.status, "not_found")

    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client_en")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client")
    def test_short_plot_skips_search_entirely(self, ru_mock, en_mock):
        result = smart_search(_smart_movie(description="Коротко."))
        self.assertEqual(result.status, "not_found")
        self.assertIn("короткое", result.message)
        ru_mock.assert_not_called()
        en_mock.assert_not_called()

    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client_en")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client")
    def test_tavily_failure_propagates_and_stops_nothing_silently(self, ru_mock, en_mock):
        # Если Tavily не работает — smart_search обязан поднять ошибку наверх,
        # чтобы очередь TMDB sync остановилась, а не молча продолжала.
        from vault.services.tavily_service import TavilySearchError

        self.search_web_mock.side_effect = TavilySearchError("Invalid API key")
        with self.assertRaises(TavilySearchError):
            smart_search(_smart_movie())
        ru_mock.assert_not_called()
        en_mock.assert_not_called()

    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.extract_web_hints")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client_en")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client")
    @patch("vault.services.tmdb_smart_search_service.is_local_ai_available", return_value=False)
    def test_web_hints_extend_queries(self, _ai_mock, ru_mock, en_mock, hints_mock):
        self.search_web_mock.return_value = "--- Поиск по название ---\nЗаголовок: X\nКонтент: Y\n"
        hints_mock.return_value = {
            "clean_title": "Ask Mom about Sex",
            "year": 2024,
            "tmdb_queries": ["Ask Mom about Sex International Cut"],
        }
        ru_mock.return_value = _FakeLangClient({})
        en_mock.return_value = _FakeLangClient({})

        result = smart_search(_smart_movie())

        self.assertEqual(result.status, "not_found")
        queried = {query for _, query, _ in ru_mock.return_value.calls}
        self.assertIn("Ask Mom about Sex International Cut", queried)

    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.extract_web_hints")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client_en")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client")
    @patch("vault.services.tmdb_smart_search_service.is_local_ai_available", return_value=False)
    def test_empty_web_context_skips_hints(self, _ai_mock, ru_mock, en_mock, hints_mock):
        self.search_web_mock.return_value = ""
        ru_mock.return_value = _FakeLangClient({})
        en_mock.return_value = _FakeLangClient({})

        smart_search(_smart_movie())

        hints_mock.assert_not_called()

    def test_pick_winner_tie_breaks_by_rank(self):
        def entry(i, score, tb=0, yb=0, order=0, eff=0.6):
            return {"movie_id": i, "score": score, "eff": eff, "tb": tb, "yb": yb, "order": order}

        self.assertIsNone(pick_winner([entry(1, 0.2)]))
        self.assertEqual(pick_winner([entry(1, 1.0), entry(2, 0.8)])["movie_id"], 1)
        tied = [entry(1, 1.0, tb=1, order=0), entry(2, 1.0, tb=3, yb=2, order=1)]
        self.assertEqual(pick_winner(tied)["movie_id"], 2)

    @patch("vault.services.tmdb_ai_matching_service.TMDBAIMatchingService.compare_plots")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client_en")
    @patch("vault.services.tmdb_smart_search_service.get_tmdb_client")
    @patch("vault.services.tmdb_smart_search_service.is_local_ai_available", return_value=True)
    def test_score_candidates_passes_dual_overview_and_context_to_ai(
        self, _ai_mock, ru_mock, en_mock, compare_mock
    ):
        compare_mock.return_value = AIPlotComparison(same_work=True, confidence=0.95, reason="Комплементарные сюжеты.")
        movie = _smart_movie()
        ru_mock.return_value = _FakeLangClient({
            "Ask Mom about Sex": [_overview_item(1, "Русское описание фильма.", release_date="2024-01-01")]
        })
        en_mock.return_value = _FakeLangClient({
            "Ask Mom about Sex": [_overview_item(1, "English overview of the film.", release_date="2024-01-01")]
        })
        result = smart_search(movie)
        self.assertEqual(result.status, "auto_match")
        self.assertEqual(result.selected_candidate.tmdb_id, 1)
        self.assertTrue(compare_mock.called)
        args, kwargs = compare_mock.call_args
        self.assertEqual(kwargs.get("title"), "Про секс спроси у мамы")
        self.assertEqual(kwargs.get("original_title"), "Ask Mom about Sex")
        self.assertEqual(kwargs.get("year"), 2024)
        self.assertIn("[English overview]:", args[1])

