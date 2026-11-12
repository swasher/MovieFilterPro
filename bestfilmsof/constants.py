"""Константы интеграции с bestfilmsof.com.

Значения проверены в прототипе `bestfilmsof/example_code` (см. его README).
"""

BASE_URL = "https://bestfilmsof.com"

# API не принимает limit больше 50 (HTTP 400).
PAGE_LIMIT = 50
REQUEST_TIMEOUT = 30

# API принимает годы начиная с 1874 (меньше — HTTP 400).
YEAR_MIN = 1874

# Наблюдаемый union жанров-слагов из ответов API.
GENRES = [
    "action",
    "adventure",
    "animation",
    "biography",
    "comedy",
    "crime",
    "documentary",
    "drama",
    "family",
    "fantasy",
    "history",
    "horror",
    "music",
    "musical",
    "mystery",
    "romance",
    "sci-fi",
    "sport",
    "thriller",
    "war",
    "western",
]

WEIGHT_KEYS = ("imdb", "critics", "awards", "boxoffice")

# Пресеты bestfilmsof («Weigh the score your way»), сумма весов = 100.
# None остаётся для custom: веса приходят из запроса.
WEIGHT_PRESETS: dict[str, dict[str, int] | None] = {
    "default": {"imdb": 30, "critics": 30, "awards": 20, "boxoffice": 20},
    "critics": {"imdb": 20, "critics": 60, "awards": 20, "boxoffice": 0},
    "crowd": {"imdb": 60, "critics": 0, "awards": 0, "boxoffice": 40},
    "awards": {"imdb": 20, "critics": 30, "awards": 50, "boxoffice": 0},
    "no-boxoffice": {"imdb": 38, "critics": 37, "awards": 25, "boxoffice": 0},
}

# Жанр «весь год» хранится в БД как пустая строка (unique-констрейнт работает).
