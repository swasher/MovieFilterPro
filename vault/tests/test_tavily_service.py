from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from moviefilter.models import UserPreferences
from vault.services.tavily_service import TavilySearchError, TavilyService


class TavilyServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="x")
        prefs = UserPreferences(user=self.user)
        prefs.tavily_api_key = "prefs-tavily-key"
        prefs.save()  # save() принудительно ставит pk=1 (синглтон)

    def test_key_read_from_preferences(self):
        self.assertEqual(TavilyService.get_api_key(), "prefs-tavily-key")
        self.assertTrue(TavilyService.is_configured())

    def test_legacy_env_key_is_ignored(self):
        # .env-fallback удалён: ключ берётся только из Preferences (см. AGENTS.md)
        prefs = UserPreferences.get()
        prefs.tavily_api_key = None
        prefs.save(update_fields=["tavily_api_key"])
        with override_settings(TAVILY_API_KEY="env-tavily-key"):
            self.assertEqual(TavilyService.get_api_key(), "")
            self.assertFalse(TavilyService.is_configured())

    def test_search_web_raises_when_key_missing(self):
        prefs = UserPreferences.get()
        prefs.tavily_api_key = None
        prefs.save(update_fields=["tavily_api_key"])
        with self.assertRaises(TavilySearchError):
            TavilyService.search_web("Title", "Original Title", "Достаточно длинный сюжет для поиска.")

    @patch("tavily.TavilyClient")
    def test_search_web_builds_context_from_two_queries(self, client_cls):
        client = MagicMock()
        client_cls.return_value = client
        client.search.return_value = {
            "results": [{"title": "T1", "content": "C1"}],
        }

        context = TavilyService.search_web(
            "Про секс спроси у мамы",
            "Ask Mom about Sex",
            "Азиз мечтает о кулинарном конкурсе, но завещание мамы ставит победу под угрозу.",
        )

        self.assertEqual(client.search.call_count, 2)
        queries = [call.kwargs["query"] for call in client.search.call_args_list]
        self.assertIn("Про секс спроси у мамы Ask Mom about Sex movie film", queries)
        self.assertTrue(any("Азиз мечтает" in q for q in queries))
        for call in client.search.call_args_list:
            self.assertEqual(call.kwargs["search_depth"], "basic")
            self.assertEqual(call.kwargs["max_results"], 5)
        self.assertIn("--- Поиск по название ---", context)
        self.assertIn("--- Поиск по сюжет ---", context)
        self.assertIn("Заголовок: T1", context)
        self.assertIn("Контент: C1", context)

    @patch("tavily.TavilyClient")
    def test_search_web_skips_plot_query_without_plot(self, client_cls):
        client = MagicMock()
        client_cls.return_value = client
        client.search.return_value = {"results": []}

        TavilyService.search_web("Title", "Original Title", "")

        self.assertEqual(client.search.call_count, 1)

    @patch("tavily.TavilyClient")
    def test_search_web_raises_tavily_search_error_on_failure(self, client_cls):
        client = MagicMock()
        client_cls.return_value = client
        client.search.side_effect = RuntimeError("Invalid API key")

        with self.assertRaises(TavilySearchError) as ctx:
            TavilyService.search_web("Title", "Original Title", "Достаточно длинный сюжет для поиска.")
        self.assertIn("Invalid API key", str(ctx.exception))

    def test_clip_plot(self):
        self.assertEqual(TavilyService._clip_plot("  коротко  ", 100), "коротко")
        clipped = TavilyService._clip_plot("a" * 600, 500)
        self.assertEqual(clipped, "a" * 500 + "...")
