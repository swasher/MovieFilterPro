from django.test import SimpleTestCase, TestCase

from ai_predict.models import PromptTemplate
from ai_predict.services import prompt as prompt_service
from ai_predict.services.engine import normalize_verdict, render_report
from ai_predict.services.local_ai import parse_json_object, strip_reasoning
from ai_predict.services.movie_card import build_movie_card
from ai_predict.services.prompt import build_system_prompt, build_user_prompt
from vault.models import Movie


class PromptTests(TestCase):
    def test_template_contains_profile(self):
        system_prompt = build_system_prompt("Люблю детективы.")

        self.assertIn("## Профиль человека", system_prompt)
        self.assertIn("Люблю детективы.", system_prompt)
        self.assertIn("Верни **только JSON**", system_prompt)
        self.assertNotIn("{{PROFILE}}", system_prompt)

    def test_default_prompt_has_no_personal_preferences(self):
        """Системный промпт должен подходить любому человеку."""
        template = prompt_service.get_default_prompt()

        for forbidden in ("детектив", "мелодрама", "фэнтези", "ужас", "Rita", "7.5", "25 лет"):
            self.assertNotIn(forbidden.lower(), template.lower())

    def test_user_prompt_contains_card(self):
        prompt = build_user_prompt({"title": "Фильм", "year": 2020})

        self.assertIn('"title": "Фильм"', prompt)


class PromptTemplateTests(TestCase):
    def test_defaults_to_bundled_prompt(self):
        state = prompt_service.get_prompt_state()

        self.assertTrue(state["is_default"])
        self.assertEqual(state["content"], state["default_content"])
        self.assertIsNone(state["updated_at"])

    def test_save_and_reset(self):
        saved = prompt_service.save_prompt_template("Свой промпт.")

        self.assertFalse(saved["is_default"])
        self.assertEqual(saved["content"], "Свой промпт.")
        self.assertEqual(prompt_service.get_prompt_template(), "Свой промпт.")
        self.assertIsNotNone(saved["updated_at"])

        reset = prompt_service.reset_prompt_template()

        self.assertTrue(reset["is_default"])
        self.assertEqual(reset["content"], reset["default_content"])
        self.assertFalse(PromptTemplate.objects.exists())

    def test_empty_prompt_is_rejected(self):
        with self.assertRaises(prompt_service.PromptError):
            prompt_service.save_prompt_template("   ")


class MovieCardTests(TestCase):
    def test_card_is_neutral_and_has_no_stop_flags(self):
        movie = Movie.objects.create(
            title="Тестовый фильм",
            year=2000,
            movie_type=Movie.MovieType.MOVIE,
            description="Описание.",
        )

        card = build_movie_card(movie)

        self.assertNotIn("hard_flags", card)
        self.assertEqual(card["year"], 2000)
        self.assertIsNotNone(card["age_years"])


class LocalAIParsingTests(SimpleTestCase):
    def test_strip_reasoning_removes_blocks(self):
        raw = "<think>долго думаю</think>\n{\"score\": 5}"
        self.assertEqual(strip_reasoning(raw), '{"score": 5}')

    def test_parse_plain_json(self):
        self.assertEqual(parse_json_object('{"score": 5}'), {"score": 5})

    def test_parse_fenced_json(self):
        self.assertEqual(parse_json_object('```json\n{"score": 7}\n```'), {"score": 7})

    def test_parse_json_with_surrounding_text(self):
        self.assertEqual(parse_json_object('Вот ответ: {"score": 2} готово'), {"score": 2})

    def test_parse_invalid_json_returns_none(self):
        self.assertIsNone(parse_json_object("не json"))
        self.assertIsNone(parse_json_object(""))


class VerdictNormalizationTests(SimpleTestCase):
    def test_score_is_clamped(self):
        self.assertEqual(normalize_verdict({"score": 42})["score"], 10)
        self.assertEqual(normalize_verdict({"score": 0})["score"], 1)

    def test_invalid_score(self):
        self.assertIsNone(normalize_verdict({"score": "хорошо"})["score"])

    def test_model_verdict_is_kept(self):
        self.assertEqual(normalize_verdict({"score": 9, "verdict": "skip"})["verdict"], "skip")
        self.assertEqual(normalize_verdict({"score": 4, "verdict": "watch"})["verdict"], "watch")
        self.assertEqual(normalize_verdict({"verdict": "MAYBE"})["verdict"], "maybe")

    def test_verdict_falls_back_to_score(self):
        # Если модель не прислала verdict — выводим его из score.
        self.assertEqual(normalize_verdict({"score": 9})["verdict"], "watch")
        self.assertEqual(normalize_verdict({"score": 5})["verdict"], "maybe")
        self.assertEqual(normalize_verdict({"score": 2})["verdict"], "skip")
        self.assertIsNone(normalize_verdict({"verdict": "что-то"})["verdict"])

    def test_invalid_verdict_falls_back_to_score(self):
        self.assertEqual(normalize_verdict({"score": 8, "verdict": "хорошо"})["verdict"], "watch")

    def test_lists_are_limited_and_cleaned(self):
        verdict = normalize_verdict({"plus": ["  а  б ", "", "в", "г", "д"]})
        self.assertEqual(verdict["plus"], ["а б", "в", "г"])

    def test_string_plus_becomes_list(self):
        self.assertEqual(normalize_verdict({"minus": "затянуто"})["minus"], ["затянуто"])

    def test_confidence_is_clamped(self):
        self.assertEqual(normalize_verdict({"confidence": 1.7})["confidence"], 1.0)
        self.assertEqual(normalize_verdict({"confidence": -3})["confidence"], 0.0)
        self.assertIsNone(normalize_verdict({"confidence": "уверен"})["confidence"])


class ReportRenderingTests(SimpleTestCase):
    def test_report_contains_verdict_and_lists(self):
        verdict = normalize_verdict(
            {
                "score": 7,
                "confidence": 0.8,
                "plus": ["Детектив"],
                "minus": ["Мелодрама"],
                "unknowns": ["Финал"],
                "summary": "Скорее да.",
            }
        )
        text = render_report(
            card={"title": "Фильм", "year": 2021},
            taste_profile=None,
            model_name="test-model",
            verdict=verdict,
        )

        self.assertIn("Профиль: не выбран", text)
        self.assertIn("Оценка: 7/10 — брать", text)
        self.assertIn("Уверенность: 0.80", text)
        self.assertIn("Плюсы:", text)
        self.assertIn("• Детектив", text)

    def test_report_without_score(self):
        verdict = normalize_verdict({})
        text = render_report(
            card={"title": "Фильм", "year": None},
            taste_profile=None,
            model_name="",
            verdict=verdict,
        )

        self.assertIn("модель не вернула score", text)
