"""
Выбор AI endpoint для стадий TMDB-матчинга Kinorium sync.

Быстрая стадия (TMDBFastAIMatchingService) использует
UserPreferences.kinorium_fast_ai_endpoint, глубокая (TMDBAIMatchingService) —
kinorium_deep_ai_endpoint. Если поле не задано — выбранный ai_endpoint.
Мастер-выключатель ai_enabled отключает обе стадии.
"""

from unittest.mock import patch

from django.test import TestCase

from core.models import AiEndpoint, UserPreferences
from vault.services.tmdb_ai_matching_service import TMDBAIMatchingService
from vault.services.tmdb_fast_ai_matching_service import TMDBFastAIMatchingService
from vault.services.tmdb_smart_search_service import is_ai_available

PLOT_A = (
    "Наследник великого дома оказывается на пустынной планете Арракис, "
    "где добывают самое ценное вещество во вселенной — спайс."
)
PLOT_B = (
    "Молодой герцог Пол Атрейдес прилетает на планету Дюна, населённую "
    "гигантскими червями, и вступает в борьбу с домом Харконненов."
)


class FakeCompletionResult:
    def __init__(self, content: str):
        self.content = content
        self.finish_reason = "stop"
        self.payload = {}


class KinoriumAiEndpointSelectionTests(TestCase):
    def setUp(self):
        self.fast = AiEndpoint.objects.create(
            name="Fast", base_url="http://fast:8000/v1", model="fast-model"
        )
        self.deep = AiEndpoint.objects.create(
            name="Deep", base_url="http://deep:8000/v1", model="deep-model"
        )
        self.selected = AiEndpoint.objects.create(
            name="Selected", base_url="http://selected:8000/v1", model="selected-model"
        )
        self.preferences = UserPreferences.get()
        self.preferences.ai_enabled = True
        self.preferences.ai_endpoint = self.selected
        self.preferences.save()

    def test_fast_stage_uses_kinorium_fast_ai_endpoint(self):
        self.preferences.kinorium_fast_ai_endpoint = self.fast
        self.preferences.save()

        with patch(
            "core.services.ai_client.post_chat_completion",
            return_value=FakeCompletionResult('{"confidence": 0.9, "reason": "Совпали имена."}'),
        ) as post:
            result = TMDBFastAIMatchingService.compare_pair(PLOT_A, PLOT_B)

        self.assertIsNotNone(result)
        self.assertEqual(post.call_args.args[0].model, "fast-model")

    def test_fast_stage_falls_back_to_selected_endpoint(self):
        with patch(
            "core.services.ai_client.post_chat_completion",
            return_value=FakeCompletionResult('{"confidence": 0.9, "reason": "Совпали имена."}'),
        ) as post:
            result = TMDBFastAIMatchingService.compare_pair(PLOT_A, PLOT_B)

        self.assertIsNotNone(result)
        self.assertEqual(post.call_args.args[0].model, "selected-model")

    def test_deep_stage_uses_kinorium_deep_ai_endpoint(self):
        self.preferences.kinorium_deep_ai_endpoint = self.deep
        self.preferences.save()

        with patch(
            "core.services.ai_client.post_chat_completion",
            return_value=FakeCompletionResult(
                '{"same_work": true, "confidence": 0.9, "reason": "Тот же фильм.", "red_flags": []}'
            ),
        ) as post:
            result = TMDBAIMatchingService.compare_plots(PLOT_A, PLOT_B, title="Дюна")

        self.assertIsNotNone(result)
        self.assertEqual(post.call_args.args[0].model, "deep-model")

    def test_deep_stage_falls_back_to_selected_endpoint(self):
        with patch(
            "core.services.ai_client.post_chat_completion",
            return_value=FakeCompletionResult(
                '{"same_work": true, "confidence": 0.9, "reason": "Тот же фильм.", "red_flags": []}'
            ),
        ) as post:
            result = TMDBAIMatchingService.compare_plots(PLOT_A, PLOT_B)

        self.assertIsNotNone(result)
        self.assertEqual(post.call_args.args[0].model, "selected-model")

    def test_ai_disabled_stops_both_stages(self):
        self.preferences.ai_enabled = False
        self.preferences.save()

        self.assertIsNone(TMDBFastAIMatchingService.compare_pair(PLOT_A, PLOT_B))
        self.assertIsNone(TMDBAIMatchingService.compare_plots(PLOT_A, PLOT_B))
        self.assertFalse(is_ai_available())

    def test_is_ai_available_uses_deep_endpoint(self):
        self.preferences.kinorium_deep_ai_endpoint = self.deep
        self.preferences.ai_endpoint = None
        self.preferences.save()

        self.assertTrue(is_ai_available())
