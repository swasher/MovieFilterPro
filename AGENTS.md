# AGENTS.md — MovieFilterPro

## Главный фокус разработки
- Самые важные приложения: `moviefilter` и `vault`.
- Смежные критичные зависимости для них: `kinozal_scan`, `kinorium`, `core`, `web_logger`.

## Project Agreements

### Vault Data Import
- Assume Vault tables are empty before import.
- No data transfer between legacy Vault schemas is required.

### Deployment Model
- The app is single-user and self-hosted.
- Authentication stays enabled.
- Keep user-related logic and models simple.
- Do not add multi-user collaboration complexity (for example, per-user comment threads is out of scope).

### Management Commands
- Run Django management commands via `uv run python manage.py <command>`.

### Search Discipline
- Use `rg`/`rg --files` for codebase search so `.rgignore` is respected.
- Do not run repository-wide recursive listing commands like `Get-ChildItem -Recurse` from the repo root unless the user explicitly asks for it.
- Use `fd` (program to find entries in your filesystem).
- Use `sg` (ast-grep, syntax-aware search and rewrite using AST patterns).
- Use `bat` for reading concrete files when syntax highlighting and line-oriented viewing are helpful.

### Search Tools
- Use `fd` for fast file and directory discovery when it is a better fit than `rg --files`.
- Use `ast-grep` for syntax-aware search/refactoring when regex-based matching is fragile.
- Use `bat` to read specific files after search; prefer it over plain `type`/`Get-Content` when available.

### Communication with user
- Using russian language.

### Scope Safety
- Редактировать системные файлы или файлы, не относящиеся к текущему Django app, только по прямому запросу пользователя.

## Быстрый локальный старт
- Установка зависимостей: `uv sync`
- Проверка проекта: `uv run python manage.py check`
- Миграции: `uv run python manage.py migrate`
- Запуск: `uv run python manage.py runserver`
- ASGI-вариант (websocket/logging): `uv run python run_daphne_debug.py`

## Переменные окружения (минимум)
- `SECRET_KEY`
- `DEBUG`
- `ENABLE_DEBUG_TOOLBAR`
- `ENABLE_BROWSER_RELOAD`
- `DATABASE_URL`

## Архитектура и потоки данных

### 1) Поток Kinozal -> RSS (`moviefilter`)
- UI скана: `kinozal_scan/templates/scan_page.html` (`/scan_page/`).
- HTMX старт скана: `kinozal_scan/htmx_views.py::scan` (`/scan/`).
- Async orchestration: `kinozal_scan/service.py::start_scan_task`.
- Основной парсер: `kinozal_scan/parse.py` (`kinozal_scan`, `parse_page`, `get_details`, `movie_audit`).
- Результат складывается в `moviefilter.models.MovieRSS`.
- Лента/фильтры/действия пользователя: `moviefilter/views.py`, `moviefilter/htmx_views.py`, `moviefilter/templates/rss.html`.

### 2) Влияние Kinorium на `moviefilter`
- Таблица `moviefilter.models.Kinorium` используется парсером для skip/partial match.
- Обновление Kinorium через UI: `kinorium/views.py` (`/table/` + загрузка 2 CSV).
- Парсер CSV: `kinorium/parse_csv.py`.

### 3) Поток Vault (`vault`)
- Основные модели: `vault/models.py`.
- Сервис статусов/рейтингов: `vault/services/movie_status_service.py`.
- Основные страницы: `vault/views.py`, `vault/templates/vault/*`.
- Роутинг: `vault/urls.py` и также legacy-роуты без префикса в `movie_filter_pro/urls.py`.
- Новый API-слой для фронта Svelte: `django-ninja` (`vault/api.py`, префикс `/api/vault/`).

### 4) Импорт данных в Vault
- Команда: `uv run python manage.py import_kinorium_csv`.
- Источник CSV: `vault/current_csv/backup_76444_*.csv`.
- Команда рассчитана на пустые таблицы `vault` и создает/связывает сущности (Movie, Person, Genre, UserMovie, UserList и т.д.).
- Очистка перед импортом: `uv run python manage.py clear_vault_data`.

## Ключевые модели, которые нужно помнить

### moviefilter
- `UserPreferences`: singleton через `pk=1`, брать только через `UserPreferences.get()`.
- `MovieRSS`: входящий поток с Kinozal и приоритетами (`HIGH/LOW/DEFER/SKIP/WAIT_TRANS/TRANS_FOUND` из `settings.py`).
- `Kinorium`: локальный кэш CSV Kinorium для матчей в сканере.

### vault
- `Movie`: центральная сущность фильмотеки.
- `Person`, `MoviePerson`: состав и роли.
- `UserMovie`: статус просмотра, избранное, рейтинг, заметка.
- `UserList`, `UserListMovie`: пользовательские списки.

## Где править по задачам
- Логика скана/фильтрации новых релизов: `kinozal_scan/parse.py`, `kinozal_scan/checks.py`.
- Действия в RSS (Hide/Defer/Wait/Download): `moviefilter/htmx_views.py`, `moviefilter/templates/partials/rss-table.html`.
- Кеш постеров RSS: `moviefilter/image_caching.py`.
- Статусы/рейтинги/системные списки Vault: `vault/services/movie_status_service.py`, `vault/views.py`.
- UI Vault: `vault/templates/vault/*`.

## Логи и realtime
- Файлы логов: `logs/debug.log`, `logs/error.log`, `logs/scan.log`.
- Websocket-канал логов: `web_logger/*`, endpoint `ws/log/`.
- Доки: `docs/LOGGING.md`, `docs/WEBSOCKET-LOGGING.md`.

## Известные несоответствия (важно перед правками)
- Устаревшие команды `moviefilter`:
  - `get_details_one_movie` и `get_all_movies_from_page` падают из-за ссылок на удаленный `moviefilter.parse`.
- `test_parse_detail.py` тоже ссылается на `moviefilter.parse` и ломает `uv run python manage.py test`.
- `vault populate_movies` в текущем виде нерабочий (устаревшие импорты/поля, не синхронизирован с текущими моделями).
- В `vault` есть рассинхрон между моделями и частью шаблонов/admin (в шаблонах местами ожидается `ImageField`-поведение `.url`, а в моделях `poster/photo` это `CharField`).
- `vault.models.Person.photo_url` использует `settings.TMDB_IMAGE_SIZE`, но этот ключ сейчас не задан в `settings.py`.

## Практическая последовательность при новой задаче
- Проверить, к какому потоку относится задача: RSS (`moviefilter`/`kinozal_scan`) или Vault (`vault`).
- Найти точку входа в URL -> view -> service/model -> template.
- Учитывать singleton-настройки через `UserPreferences.get()`.
- Для изменений в Vault-статусах идти через `MovieStatusService`, а не дублировать логику во views.
- Для задач импорта в Vault предполагать чистые таблицы (согласно соглашениям выше).

## Шапки для сервисного слоя

Используй такие шапки, чтобы отделить Application от Domain логики:

```
# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #
```

```
# ------------------------------------ #
#            DOMAIN LAYER              #
# ------------------------------------ #
```
