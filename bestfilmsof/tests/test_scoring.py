from types import SimpleNamespace

from django.test import SimpleTestCase

from bestfilmsof.scoring import clamp_weight, parse_weights, rescore


class RescoreTests(SimpleTestCase):
    def entry(self, **kwargs):
        values = {
            "comp_imdb": None,
            "comp_critics": None,
            "comp_awards": None,
            "comp_boxoffice": None,
            "fb_critics": None,
            "fb_boxoffice": None,
        }
        values.update(kwargs)
        return SimpleNamespace(**values)

    def test_formula(self):
        entry = self.entry(
            comp_imdb=0.5,
            comp_critics=0.25,
            comp_awards=0.1,
            comp_boxoffice=0.2,
        )
        score = rescore(
            entry, {"imdb": 20, "critics": 60, "awards": 20, "boxoffice": 0}
        )
        self.assertEqual(score, 27.0)

    def test_uses_fallback_for_missing_components(self):
        entry = self.entry(
            comp_imdb=0.5,
            comp_critics=None,
            fb_critics=0.3,
            comp_boxoffice=None,
            fb_boxoffice=0.4,
        )
        score = rescore(
            entry, {"imdb": 50, "critics": 25, "awards": 0, "boxoffice": 25}
        )
        self.assertEqual(score, 42.5)

    def test_returns_none_when_component_and_fallback_missing(self):
        entry = self.entry(comp_imdb=0.5)
        self.assertIsNone(rescore(entry, {"critics": 100}))

    def test_zero_weights_fall_back_to_none(self):
        entry = self.entry(comp_imdb=0.5)
        self.assertIsNone(rescore(entry, {"imdb": 0}))

    def test_weight_bounds(self):
        self.assertEqual(clamp_weight(-5), 0)
        self.assertEqual(clamp_weight(150), 100)
        self.assertEqual(clamp_weight("42"), 42)
        self.assertEqual(clamp_weight("bad"), 0)

    def test_parse_weights_fills_all_keys(self):
        weights = parse_weights({"imdb": 10, "unknown": 1})
        self.assertEqual(weights, {"imdb": 10, "critics": 0, "awards": 0, "boxoffice": 0})
