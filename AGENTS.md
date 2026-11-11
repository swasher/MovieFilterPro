# AGENTS.md — MovieFilterPro

## Главный фокус разработки
- Самые важные приложения: `moviefilter` и `vault`.
- Смежные критичные зависимости для них: `kinozal_scan`, `kinorium`, `core`, `web_logger`.

## Project Agreements

### Line Endings
- Все файлы в репозитории хранятся с LF (`\n`), не CRLF.
- При создании/редактировании файлов всегда использовать LF.
- `core.autocrlf=false`, правила задаются через `.gitattributes`.

### Конфигурация: .env vs Preferences
- `.env` (и `config(...)` в `settings.py`) — только «системные» данные: SECRET_KEY, ALLOWED_HOSTS, DEBUG, подключения к БД, HUEY и т.п.
- API-ключи и URL-ы внешних сервисов (TMDB, OMDB, Tavily, SearXNG, Plex, cookie Kinozal и пр.) настраиваются ИСКЛЮЧИТЕЛЬНО через пользовательский интерфейс (UserPreferences + страница Preferences).
- Не добавляй для сервисных настроек fallback-и вида `*_API_KEY` / `*_URL` в `.env`/settings — код приложения их не читает.
- Исключение — dev-машина: в локальном `.env` на самом деле есть все живые ключи, и их можно использовать во время разработки (отладка идей, standalone-скрипты). На продакшне в `.env` этих ключей нет — там только «системные» переменные; приложение в любом случае берёт сервисные настройки только из Preferences.

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
- NEVER change DB data! Ты видишь только тестувую (dev) базу данных, и с данными работать не должен!

### Local DB Data — AI Must Not Touch
- Данные в локальной БД — одноразовые. Не добавляй никакую логику, миграции или код для сохранения и поддержки консистентности старых данных при изменении схемы.
- Считать все строки в таблицах валидными для текущей задачи.
- Но нужно думать о том, что миграции и изменения должны корректно "лечь" на production db.

### Deployment Model
- The app is single-user and self-hosted.
- Authentication stays enabled.
- Keep user-related logic and models simple.
- Do not add multi-user collaboration complexity (for example, per-user comment threads is out of scope).

### Management Commands
- Run Django management commands via `uv run python manage.py <command>`.

### Dev Servers and Ports (для AI-агента)
- У пользователя свои порты: backend `8000`, frontend `5173`. Агент их не занимает и не переиспользует уже запущенные процессы пользователя.
- Свои dev-серверы агент поднимает только на отдельных свободных портах: backend начиная с `8001`, frontend начиная с `5174`, и передаёт порт явно. `run_daphne_debug.py` жёстко зашит на `8000` — для своего сервера запускать daphne напрямую (`uv run daphne -b 127.0.0.1 -p 8001 movie_filter_pro.asgi:application`).
- Для Vite обязателен `--strictPort`: без него Vite молча займёт `5173`, если сервер пользователя не запущен.
- Свой frontend должен проксировать `/api` на свой backend-порт. Цель прокси задаётся переменной окружения `VITE_BACKEND_URL` (по умолчанию — `http://127.0.0.1:8000`).
- Готовность своих серверов проверять по TCP-порту, а не по HTTP-ответу на `/`: Django на `/` отдаёт `404` (SPA обслуживает Vite), а `Invoke-WebRequest` в PowerShell 5.1 на не-2xx бросает исключение — цикл «жду 200» никогда не увидит успех и выжжет весь таймаут. Готовый `Wait-Port` — в `.agents/skills/dev-login/SKILL.md`; HTTP-вариант для backend — `GET /api/auth/session/` (всегда 200 JSON).
- `127.0.0.1` и `localhost` — не одно и то же: Vite с хостом `localhost` слушает только `::1`, daphne с `-b 127.0.0.1` — только IPv4. Проверять порты и открывать frontend по имени `localhost` (оно покрывает оба семейства), а не по `127.0.0.1`.
- Нормальный старт: daphne ~1 с, Vite ~2.5 с (плюс первая сборка). Если порт не поднялся за 10–15 с — это ошибка запуска: смотреть вывод фонового процесса, а не ждать дольше.
- Агент обязан остановить свой сервер сразу после получения результата и убедиться, что порт освободился.
- Не запускать второй HUEY-воркер и не останавливать/перезапускать процессы пользователя (daphne, Vite, PostgreSQL).
- Если проверка возможна тестами или `manage.py`-командами, dev-серверы не поднимать вовсе.
- Общие ресурсы у двух backend-процессов одни: PostgreSQL, каталог `cache/`, файлы логов. Это допустимо (запись в кеш атомарная), но single-flight загрузок работает только в пределах процесса.

### Проверки и in-app браузер
- Рутинные визуальные проверки — на стороне пользователя. Агент не открывает in-app браузер ради «посмотреть, как выглядит»: это дорого по токенам и всё равно субъективно.
- Браузер агент использует только по явной договорённости и только для конкретной технической диагностики, которую нельзя получить иначе: сетевые запросы (сколько раз и в каком порядке), console-ошибки, пересоздание DOM.
- Логин: агент не создаёт сессии/пользователей в БД. Для авторизованных проверок используется временный dev-аккаунт, логин и пароль которого пользователь хранит в файле `.env.agent` в корне проекта (`AGENT_USERNAME`, `AGENT_PASSWORD`). Файл добавлен в `.gitignore` и в репозиторий не попадает.
- Эти креды созданы специально для агента и считаются НЕ секретными: их можно подставлять в запросы и выводить при отладке. Ограничения — не коммитить `.env.agent` и не копировать значения в `.env`/`.env.production` или другие файлы репозитория.
- Агент читает `.env.agent` только когда действительно нужен вход (например, для диагностики в in-app браузере).
- Готовый рецепт входа и проверки авторизации — скилл `.agents/skills/dev-login/SKILL.md`.
- Вход выполнять через `localhost`: куки не учитывают порт, поэтому одна сессия работает на `8000`/`8001`/`5173`/`5174`.
- Backend по умолчанию проверяется тестами (`uv run python manage.py test ...`) и прямыми вызовами сервисов; frontend — `svelte-check`/сборкой и визуальной проверкой пользователя.

### Communication with user
- Using russian language.
- Не удалять и не переписывать без явной необходимости существующие фрагменты пользовательского кода, даже если они выглядят избыточными, дублирующими или могут быть заменены более "чистым" вариантом.
- Сохранять существующие комментарии, закомментированные команды, альтернативные варианты запуска, явные проверки ошибок и другой пользовательский контекст, если они не мешают решению задачи.
- Если удаление, упрощение или замена существующего куска кода не являются прямой частью задачи, сначала явно согласовать это с пользователем.

### Отметка выполненной работы в TODO.md
- Когда пользователь просит отметить выполненную работу в `TODO.md`, можно отмечать только уже имеющиеся в файле пункты (задачи), соответствующие выполненной работе.
- Создавать новые пункты нельзя!
- Если подходящий пункт не найден, нужно просто сообщить об этом пользователю.

### Scope Safety
- Редактировать системные  файлы (корневые файлы проекта) или файлы, не относящиеся к текущему Django app, только по прямому запросу пользователя.

## Архитектура и потоки данных

### 1) Поток Kinozal -> RSS (`moviefilter`)
- UI скана: `front/src/routes/scan/+page.svelte`.
- Старт/статус/отмена скана: Ninja endpoints в `kinozal_scan/api.py`.
- Async orchestration: `kinozal_scan/service.py::start_scan_task`.
- Основной парсер: `kinozal_scan/parse.py` (`kinozal_scan`, `parse_page`, `get_details`, `movie_audit`).
- Результат складывается в `moviefilter.models.MovieRSS`.
- Лента/фильтры/действия пользователя: `front/src/routes/kinozal/+page.svelte`, `moviefilter/api.py`.
- Транспорт HTTP: `moviefilter/kinozal/kinozal_client.py` (`KinozalClient.get_html_response`).
  Единая точка всех GET-запросов к Kinozal (скан, поиск раздач, детали). Внутри — обход
  Cloudflare: HTTP-first, при детекции челленджа браузерная эскалация через Scrapling
  `StealthyFetcher` (`moviefilter/kinozal/cloudflare.py`). Парсеры о CF не знают и получают
  обычный `requests.Response`.

### 2) Влияние Kinorium на `moviefilter`
- Таблица `moviefilter.models.Kinorium` используется парсером для skip/partial match.
- Табличный Django UI и HTMX загрузка Kinorium удалены; модельный кэш Kinorium продолжает использоваться сканером.

### 3) Поток Vault (`vault`)
- Основные модели: `vault/models.py`.
- Сервисы статусов/рейтингов/TMDB: `vault/services/*`.
- API-слой для фронта Svelte: `django-ninja` (`vault/api.py`, префикс `/api/vault/`).
- UI Vault: `front/src/routes/**`.
- Старый Django UI Vault удален; пользовательские страницы обслуживает Svelte, данные и действия — `vault/api.py` и `vault/services/*`.

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
- `Person`, `MoviePerson`: состав и роли; `FavoritePerson`: избранные персоны.
- `UserMovie`: статус просмотра, избранное, рейтинг, заметка.
- `UserList`, `UserListMovie`: пользовательские списки; `SidebarLayout`: порядок в сайдбаре.
- `Season`, `Episode`, `UserSeason`: сезоны/эпизоды и их статусы.
- `VaultConnectionEvent`: события Kinozal/Vault связки.
- `TMDBSyncQueueItem`: очередь TMDB sync.

## Где править по задачам
- Логика скана/фильтрации новых релизов: `kinozal_scan/parse.py`, `kinozal_scan/checks.py`.
- Действия в Kinozal UI (Hide/Defer/Wait/Download): `front/src/routes/kinozal/+page.svelte`, `moviefilter/api.py`.
- Кеш постеров RSS: `moviefilter/image_caching.py`.
- Статусы/рейтинги/системные списки Vault: `vault/services/movie_status_service.py`.
- Сезоны/эпизоды Vault: `vault/services/season_status_service.py`.
- TMDB поиск/matching/sync/import для Vault: `vault/services/tmdb_*.py`.
- UI Vault (Svelte): `front/src/routes/**`.
- API Vault: `vault/api.py`.

## Write-back (Vault → TMDB)

Если задача затрагивает **обратную синхронизацию Vault в TMDB** (watchlist,
favorites, rating, списки, TMDB Lists, очередь writeback, асинхронный конвейер),
сначала прочитай `docs/WRITEBACK_IMPLEMENTATION.md` — там описание архитектуры и
места правок. Краткий список: сигналы → `vault/signals.py`, диспетчер HUEY →
`vault/services/tmdb_writeback_dispatch.py`, фоновые задачи → `vault/tasks.py`,
вся прикладная логика → `vault/services/tmdb_writeback_service.py`.

## Логи и realtime
- Файлы логов: `logs/debug.log`, `logs/error.log`, `logs/scan.log`.
- Websocket-канал логов: `web_logger/*`, endpoint `ws/log/`.
- Доки: `docs/LOGGING.md`, `docs/WEBSOCKET-LOGGING.md`.

## Frontend: текущее состояние
- Основной паттерн интеграции: `front` (SvelteKit) -> SvelteKit proxy routes -> `django-ninja` endpoints (в `vault/api.py`).
- Для локального single-user сценария глобальный `SSR` в `front` отключен, приложение ведет себя как SPA.
- Аутентификация — стандартная Django session auth (`django.contrib.auth`), без JWT/token-based схемы.
- В API использовать реальный `request.user`; если endpoint требует пользователя — возвращать `401`, без `User.objects.first()` и других single-user fallback.
- `tmdb_adapter.client_singleton` — инфраструктурный TMDB-клиент из `UserPreferences`; auth/logout endpoints находятся в `vault/api.py`. Прикладную логику поиска, matching, sync и import для Vault держать в `vault/services/*`.
- `vault` полностью перенесен в новый frontend (списки, фильтры, поиск, детали, персоны, статусы, рейтинг, пользовательские списки, TMDB sync, сезоны). Старые Django templates, UI routes и HTMX handlers удалены.
- В `front/src/routes/**` есть и другие перенесенные страницы: `kinozal`, `scan`, `plex`, `tmdb`, `tmdb-sync`, `preferences`.

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
