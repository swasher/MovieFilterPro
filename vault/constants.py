# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #

# Единый источник правды для имён системных списков Vault.
# Все отображаемые строки системных списков хранятся здесь.
# Остальной код проекта импортирует эти константы, а не хардкодит строки.

# Ключи системных списков (совпадают с UserList.ListType)
WATCHED = 'watched'
WILL_WATCH = 'will_watch'
WONT_WATCH = 'wont_watch'
FAVORITES = 'favorites'

# Отображаемые имена
WATCHED_LABEL = 'Просмотрено'
WILL_WATCH_LABEL = 'Буду смотреть'
WONT_WATCH_LABEL = 'Не интересует'
FAVORITES_LABEL = 'Избранное'

# Маппинг ключ -> отображаемое имя (для views, api, sidebar)
SYSTEM_LIST_LABELS: dict[str, str] = {
    WATCHED: WATCHED_LABEL,
    WILL_WATCH: WILL_WATCH_LABEL,
    WONT_WATCH: WONT_WATCH_LABEL,
    FAVORITES: FAVORITES_LABEL,
}

# Маппинг watch_status int -> label (для моделей и парсеров)
WATCH_STATUS_LABELS: dict[int, str] = {
    1: WATCHED_LABEL,
    2: WILL_WATCH_LABEL,
    3: WONT_WATCH_LABEL,
}

# Обратный маппинг label -> watch_status (для парсера kinorium)
LABEL_TO_WATCH_STATUS: dict[str, int] = {
    WATCHED_LABEL: 1,
    WILL_WATCH_LABEL: 2,
    WONT_WATCH_LABEL: 3,
}

# Маппинг list_title из CSV -> watch_status (для import_kinorium_csv)
CSV_LIST_TITLE_TO_WATCH_STATUS: dict[str, int] = {
    WILL_WATCH_LABEL: 2,
    'Просмотрен': 1,
    WONT_WATCH_LABEL: 3,
}

# Набор имён системных списков (для import_kinorium_csv)
SYSTEM_LIST_TITLES: set[str] = {
    WATCHED_LABEL,
    WILL_WATCH_LABEL,
    WONT_WATCH_LABEL,
}

# Имя TMDB-зеркального списка для SKIP
SKIP_LIST_NAME = WONT_WATCH_LABEL

# Имя TMDB-зеркального списка для WATCHED
WATCHED_LIST_NAME = WATCHED_LABEL
