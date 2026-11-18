from datetime import datetime

from django.test import SimpleTestCase

from kinozal_scan.parse import parse_header


class ParseHeaderTests(SimpleTestCase):
    def test_normal_format(self):
        title, original_title, year = parse_header(
            "Красная жара / Red Heat / 1988 / ПМ / UHD / BDRip (1080p)"
        )

        self.assertEqual(title, "Красная жара")
        self.assertEqual(original_title, "Red Heat")
        self.assertEqual(year, "1988")

    def test_russian_without_original_title(self):
        title, original_title, year = parse_header("Наследие / 2023 / РУ, СТ / WEB-DL (1080p)")

        self.assertEqual(title, "Наследие")
        self.assertEqual(original_title, "")
        self.assertEqual(year, "2023")

    def test_no_ru_no_original_title(self):
        title, original_title, year = parse_header("Карточный долг / 2023 / ДБ / WEB-DL (1080p)")

        self.assertEqual(title, "Карточный долг")
        self.assertEqual(original_title, "")
        self.assertEqual(year, "2023")

    def test_year_range_takes_first_four_digits(self):
        title, original_title, year = parse_header(
            "Голый пистолет (Коллекция) / Naked Gun: Collection / 1982-1994 / ПМ, ПД"
        )

        self.assertEqual(title, "Голый пистолет (Коллекция)")
        self.assertEqual(original_title, "Naked Gun: Collection")
        self.assertEqual(year, "1982")

    def test_year_list_takes_first_four_digits(self):
        title, original_title, year = parse_header(
            "Клетка для чудаков (Трилогия) / La Cage aux folles I, II, III / 1978, 1980, 1985 / ПМ, ПД"
        )

        self.assertEqual(title, "Клетка для чудаков (Трилогия)")
        self.assertEqual(original_title, "La Cage aux folles I, II, III")
        self.assertEqual(year, "1978")

    def test_malformed_header_without_slashes_takes_first_five_words(self):
        head = "Просто Длинное Название Фильма Без Всяких Слешей"
        title, original_title, year = parse_header(head)

        self.assertEqual(title, "Просто Длинное Название Фильма Без")
        self.assertEqual(original_title, "")
        self.assertEqual(year, str(datetime.now().year))

    def test_malformed_header_with_slash_takes_prefix(self):
        title, original_title, year = parse_header("Какой-то фильм / какое-то кривое продолжение")

        self.assertEqual(title, "Какой-то фильм")
        self.assertEqual(original_title, "")
        self.assertEqual(year, str(datetime.now().year))
