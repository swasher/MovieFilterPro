# AGENTS.md — MovieFilterPro

## Главный фокус разработки
- Самые важные приложения: `moviefilter` и `vault`.
- Смежные критичные зависимости для них: `kinozal_scan`, `kinorium`, `core`, `web_logger`.

## Project Agreements

### Architecture Transition
- Проект находится в процессе перехода на новую архитектуру.
- Django остается backend-слоем и источником данных.
- Новый frontend постепенно переносится на Svelte и живет в `front/`.
- Перенос делается инкрементально, без разрушения и без принудительного удаления старого Django UI.
- Legacy Django templates/views продолжают работать параллельно, пока новые сценарии не перенесены полностью.
- Новый frontend общается с backend через `django-ninja` API.

### Frontend Stack Rules
- Новый frontend: `Svelte 5` с runes only.
- Использовать только runes-синтаксис (`$state`, `$derived`, `$effect`, `$props`, snippets и т.д.).
- Не использовать устаревший синтаксис Svelte 3/4.
- UI-слой: только `shadcn-svelte`.
- Если нужный `shadcn-svelte` компонент отсутствует, сначала попросить пользователя установить его, а не городить кастомную замену.
- Папка нового frontend: `front/`.

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
- Use `semblance_search` (MCP) as the primary tool for codebase search — it provides AST-aware results with exact file paths and line numbers.
- Use `rg`/`rg --files` for text-based search in any files (logs, configs, templates) so `.rgignore` is respected.
- Do not run repository-wide recursive listing commands like `Get-ChildItem -Recurse` from the repo root unless the user explicitly asks for it.
- Use `fd` (program to find entries in your filesystem).
- Use `sg` (ast-grep, syntax-aware search and rewrite using AST patterns) for refactoring.
- Use `bat` for reading concrete files when syntax highlighting and line-oriented viewing are helpful.

### Search Tools
- Use `fd` for fast file and directory discovery when it is a better fit than `rg --files`.
- Use `ast-grep` for syntax-aware search/refactoring when regex-based matching is fragile.
- Use `bat` to read specific files after search; prefer it over plain `type`/`Get-Content` when available.

### Communication with user
- Using russian language.
- Не удалять и не переписывать без явной необходимости существующие фрагменты пользовательского кода, даже если они выглядят избыточными, дублирующими или могут быть заменены более "чистым" вариантом.
- Сохранять существующие комментарии, закомментированные команды, альтернативные варианты запуска, явные проверки ошибок и другой пользовательский контекст, если они не мешают решению задачи.
- Если удаление, упрощение или замена существующего куска кода не являются прямой частью задачи, сначала явно согласовать это с пользователем.

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
- `vault` сейчас является основным app для поэтапного переноса в новый Svelte frontend.

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
  - В `vault` есть рассинхрон между моделями и частью шаблонов/admin (в шаблонах местами ожидается `ImageField`-поведение `.url`, а в моделях `poster/photo` это `CharField`).
  - `vault.models.Person.photo_url` использует `settings.TMDB_IMAGE_SIZE`, но этот ключ сейчас не задан в `settings.py`.

## Практическая последовательность при новой задаче
- Проверить, к какому потоку относится задача: RSS (`moviefilter`/`kinozal_scan`) или Vault (`vault`).
- Найти точку входа в URL -> view -> service/model -> template.
- Учитывать singleton-настройки через `UserPreferences.get()`.
- Для изменений в Vault-статусах идти через `MovieStatusService`, а не дублировать логику во views.
- Для задач импорта в Vault предполагать чистые таблицы (согласно соглашениям выше).

## Текущее состояние миграции Frontend
- Новый frontend уже поднят в `front/` и подключен к Django backend.
- Основной паттерн интеграции: `front` -> SvelteKit proxy routes -> `django-ninja` endpoints в `vault/api.py`.
- Для локального single-user сценария глобальный `SSR` в `front` отключен, приложение ведет себя как SPA.
- Аутентификация для нового Svelte frontend остается на стандартной Django session auth (`django.contrib.auth`).
- Svelte используется только как UI-слой для login/logout/session state, без отдельной JWT/token-based схемы.
- В новом frontend и API-слоях использовать реальный `request.user`, а не fallback-пользователя.
- Не подставлять `User.objects.first()` или аналогичные single-user fallback-механизмы в API.
- Если endpoint требует пользователя, он должен возвращать `401`, а не молча работать от имени "дефолтного" пользователя.
- Для текущего self-hosted/single-user сценария предпочитать простую Django session auth реализацию вместо усложненной auth-архитектуры.
- Перенос `vault` находится в продвинутой стадии: базовый список фильмов, sidebar-фильтры, поиск, сортировка, детальная страница фильма, страница персоны, статусы, рейтинг, пользовательские списки на странице фильма и TMDB sync уже работают в новом frontend.
- TMDB flow в новом frontend уже поддерживает:
  - `ok`
  - `needs_confirmation` (один неуверенный кандидат)
  - `needs_user_choice` (несколько кандидатов)
- `tmdb_adapter` — инфраструктурный слой для TMDB:
  - `tmdb_adapter.client_singleton.get_tmdb_client()` создает и кеширует `TMDbAPIs` клиент с текущими ключами из `UserPreferences`.
  - `tmdb_adapter.auth` отвечает за TMDB auth / logout flow и сброс singleton-клиента.
  - Прикладную логику поиска, matching, sync и import для Vault держать в `vault/services/*`, а не в `tmdb_adapter`.
- При переносе новых сценариев для `vault`:
  - не менять модели без явной необходимости;
  - не ломать существующий Django UI;
  - по возможности сохранять сервисный слой и добавлять новые API/view-слои поверх него.

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
