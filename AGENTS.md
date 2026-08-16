# AGENTS.md — MovieFilterPro

## Главный фокус разработки
- Самые важные приложения: `moviefilter` и `vault`.
- Смежные критичные зависимости для них: `kinozal_scan`, `kinorium`, `core`, `web_logger`.

## Project Agreements

### Architecture Transition
- Проект перешел с импользования django-фронтэнда на svelte фронтэнд. 
- Django фронтенд остается пока в виде legacy.
- Svelte frontend общается с backend через `django-ninja` API.

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

### Communication with user
- Using russian language.
- Не удалять и не переписывать без явной необходимости существующие фрагменты пользовательского кода, даже если они выглядят избыточными, дублирующими или могут быть заменены более "чистым" вариантом.
- Сохранять существующие комментарии, закомментированные команды, альтернативные варианты запуска, явные проверки ошибок и другой пользовательский контекст, если они не мешают решению задачи.
- Если удаление, упрощение или замена существующего куска кода не являются прямой частью задачи, сначала явно согласовать это с пользователем.

### Scope Safety
- Редактировать системные  файлы (корневые файлы проекта) или файлы, не относящиеся к текущему Django app, только по прямому запросу пользователя.

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
- Сервисы статусов/рейтингов/TMDB: `vault/services/*`.
- API-слой для фронта Svelte: `django-ninja` (`vault/api.py`, префикс `/api/vault/`).
- UI Vault: `front/src/routes/**`.
- Legacy-слой (Django-шаблоны): `vault/views.py`, `vault/templates/vault/*`, роуты в `vault/urls.py` и без префикса в `movie_filter_pro/urls.py` — только для обратной совместимости.

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
- Статусы/рейтинги/системные списки Vault: `vault/services/movie_status_service.py`.
- UI Vault (Svelte): `front/src/routes/**`.
- API Vault: `vault/api.py`.

## Логи и realtime
- Файлы логов: `logs/debug.log`, `logs/error.log`, `logs/scan.log`.
- Websocket-канал логов: `web_logger/*`, endpoint `ws/log/`.
- Доки: `docs/LOGGING.md`, `docs/WEBSOCKET-LOGGING.md`.

## Frontend: текущее состояние
- Основной паттерн интеграции: `front` (SvelteKit) -> SvelteKit proxy routes -> `django-ninja` endpoints (в `vault/api.py`).
- Для локального single-user сценария глобальный `SSR` в `front` отключен, приложение ведет себя как SPA.
- Аутентификация — стандартная Django session auth (`django.contrib.auth`), без JWT/token-based схемы.
- В API использовать реальный `request.user`; если endpoint требует пользователя — возвращать `401`, без `User.objects.first()` и других single-user fallback.
- `tmdb_adapter` — инфраструктурный слой TMDB (клиент из `UserPreferences`, auth/logout, сброс singleton). Прикладную логику поиска, matching, sync и import для Vault держать в `vault/services/*`.
- `vault` полностью перенесен в новый frontend (списки, фильтры, поиск, детали, персоны, статусы, рейтинг, пользовательские списки, TMDB sync, сезоны). Django-шаблоны `vault` остаются legacy.

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
