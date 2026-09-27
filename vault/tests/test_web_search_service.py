from unittest.mock import MagicMock, patch

import requests
from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from moviefilter.models import UserPreferences
from vault.services.web_search_service import WebSearchError, WebSearchService


PLOT = "Азиз мечтает о кулинарном конкурсе, но завещание мамы ставит победу под угрозу."


def _searxng_response(results):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"results": results}
    return response


class WebSearchProviderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="x")
        prefs = UserPreferences(user=self.user)
        prefs.tavily_api_key = "prefs-tavily-key"
        prefs.save()  # save() принудительно ставит pk=1 (синглтон)

    def test_tavily_is_default_provider(self):
        self.assertEqual(WebSearchService.get_provider(), WebSearchService.PROVIDER_TAVILY)
        self.assertTrue(WebSearchService.is_configured())

    def test_searxng_url_from_prefs_wins_over_tavily_key(self):
        prefs = UserPreferences.get()
        prefs.searxng_url = "http://localhost:8087/search"
        prefs.save(update_fields=["searxng_url"])
        self.assertEqual(WebSearchService.get_provider(), WebSearchService.PROVIDER_SEARXNG)
        self.assertEqual(WebSearchService.provider_label(), "SearXNG")

    def test_legacy_env_settings_are_ignored(self):
        # .env-fallback удалён (см. AGENTS.md): SEARXNG_URL/TAVILY_API_KEY в settings
        # больше не влияют на выбор провайдера — только Preferences.
        prefs = UserPreferences.get()
        prefs.tavily_api_key = None
        prefs.searxng_url = None
        prefs.save(update_fields=["tavily_api_key", "searxng_url"])
        with override_settings(SEARXNG_URL="http://localhost:8087/search", TAVILY_API_KEY="env-key"):
            self.assertEqual(WebSearchService.get_provider(), "")
            self.assertFalse(WebSearchService.is_configured())

    def test_not_configured_without_any_provider(self):
        prefs = UserPreferences.get()
        prefs.tavily_api_key = None
        prefs.save(update_fields=["tavily_api_key"])
        self.assertFalse(WebSearchService.is_configured())
        with self.assertRaises(WebSearchError):
            WebSearchService.search_web("Title", "Original Title", PLOT)

    @patch("tavily.TavilyClient")
    @patch("requests.get")
    def test_dispatch_prefers_searxng_when_both_configured(self, get_mock, client_cls):
        prefs = UserPreferences.get()
        prefs.searxng_url = "http://localhost:8087/search"
        prefs.save(update_fields=["searxng_url"])
        get_mock.return_value = _searxng_response([{"title": "T", "content": "C"}])

        WebSearchService.search_web("Title", "Original Title", PLOT)

        get_mock.assert_called()
        client_cls.assert_not_called()


class SearXNGSearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="x")
        prefs = UserPreferences(user=self.user)
        prefs.searxng_url = "http://localhost:8087/search"
        prefs.save()

    @patch("requests.get")
    def test_builds_context_from_two_queries(self, get_mock):
        get_mock.return_value = _searxng_response(
            [
                {"title": "T1", "content": "C1", "url": "http://x/1"},
                {"title": "T2", "content": "", "url": "http://x/2"},
            ]
        )

        context = WebSearchService.search_web(
            "Про секс спроси у мамы",
            "Ask Mom about Sex",
            PLOT,
        )

        self.assertEqual(get_mock.call_count, 2)
        first_params = get_mock.call_args_list[0].kwargs["params"]
        self.assertEqual(first_params["format"], "json")
        self.assertEqual(first_params["language"], "ru-RU")
        self.assertIn("Про секс спроси у мамы Ask Mom about Sex movie film", first_params["q"])
        second_params = get_mock.call_args_list[1].kwargs["params"]
        self.assertTrue(second_params["q"].startswith("Азиз мечтает"))
        self.assertIn("--- Поиск по название ---", context)
        self.assertIn("--- Поиск по сюжет ---", context)
        self.assertIn("Заголовок: T1", context)
        self.assertIn("Контент: C1", context)
        # Пустой content -> fallback на url, а не потеря результата
        self.assertIn("Контент: http://x/2", context)

    @patch("requests.get")
    def test_skips_plot_query_without_plot(self, get_mock):
        get_mock.return_value = _searxng_response([])

        WebSearchService.search_web("Title", "Original Title", "")

        self.assertEqual(get_mock.call_count, 1)

    @patch("requests.get")
    def test_caps_results_at_max_results(self, get_mock):
        get_mock.return_value = _searxng_response(
            [{"title": f"T{i}", "content": f"C{i}"} for i in range(10)]
        )

        context = WebSearchService.search_web("Title", "Original Title", "")

        self.assertEqual(context.count("Заголовок:"), WebSearchService.MAX_RESULTS)

    @patch("requests.get")
    def test_403_mentions_json_format(self, get_mock):
        response = MagicMock()
        response.status_code = 403
        get_mock.return_value = response

        with self.assertRaises(WebSearchError) as ctx:
            WebSearchService.search_web("Title", "Original Title", PLOT)
        self.assertIn("403", str(ctx.exception))
        self.assertIn("JSON", str(ctx.exception))

    @patch("requests.get")
    def test_non_json_response_raises(self, get_mock):
        response = MagicMock()
        response.status_code = 200
        response.json.side_effect = ValueError("not json")
        get_mock.return_value = response

        with self.assertRaises(WebSearchError) as ctx:
            WebSearchService.search_web_via_searxng("Title", "Original Title", PLOT)
        self.assertIn("не JSON", str(ctx.exception))

    @patch("requests.get", side_effect=requests.ConnectionError("connection refused"))
    def test_connection_error_raises(self, _get_mock):
        with self.assertRaises(WebSearchError) as ctx:
            WebSearchService.search_web("Title", "Original Title", PLOT)
        self.assertIn("SearXNG", str(ctx.exception))

    @patch("requests.get")
    def test_url_argument_overrides_prefs(self, get_mock):
        # Явный url-аргумент важнее Preferences (нужно для скриптов сравнения)
        get_mock.return_value = _searxng_response([])

        WebSearchService.search_web_via_searxng(
            "Title", "Original Title", PLOT, url="http://override/search"
        )

        self.assertEqual(get_mock.call_args.args[0], "http://override/search")


class TavilyForcedSearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="x")
        prefs = UserPreferences(user=self.user)
        prefs.tavily_api_key = "prefs-tavily-key"
        prefs.save()

    @patch("tavily.TavilyClient")
    def test_forced_tavily_ignores_searxng_pref(self, client_cls):
        prefs = UserPreferences.get()
        prefs.searxng_url = "http://localhost:8087/search"
        prefs.save(update_fields=["searxng_url"])
        client = MagicMock()
        client_cls.return_value = client
        client.search.return_value = {"results": [{"title": "T", "content": "C"}]}

        context = WebSearchService.search_web_via_tavily("Title", "Original Title", PLOT)

        self.assertEqual(client.search.call_count, 2)
        for call in client.search.call_args_list:
            self.assertEqual(call.kwargs["search_depth"], "basic")
            self.assertEqual(call.kwargs["max_results"], 5)
        self.assertIn("Контент: C", context)

    @patch("tavily.TavilyClient")
    def test_tavily_failure_raises_web_search_error(self, client_cls):
        client = MagicMock()
        client_cls.return_value = client
        client.search.side_effect = RuntimeError("Invalid API key")

        with self.assertRaises(WebSearchError) as ctx:
            WebSearchService.search_web_via_tavily("Title", "Original Title", PLOT)
        self.assertIn("Invalid API key", str(ctx.exception))
