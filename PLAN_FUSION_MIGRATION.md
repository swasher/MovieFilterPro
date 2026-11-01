# План миграции `tmdbapis` → `tmdbfusion`

## 1. Короткий вывод

Миграция технически возможна, но это **не замена импорта**: `tmdbfusion 0.2.0` — молодая библиотека (один релиз, ~21 коммит), и в текущем виде она не покрывает 6 сценариев, на которых держатся Vault и write-back.

Рекомендуемый путь — **адаптер `tmdb_adapter` + DTO**:
- `tmdb_adapter` остаётся единственным местом, где импортируется `tmdbfusion`;
- сервисы `vault/services/*` получают стабильные доменные DTO и не зависят от библиотеки;
- бизнес-логика матчинга, скоринга, AI-resolver, синка и write-back **не меняется**;
- миграция БД не требуется.

Оценка: **7–10 рабочих дней** без форка библиотеки, **+1–2 дня**, если понадобится форк/патчи. Календарно — около 2 недель с тестированием.

---

## 2. Что используется сейчас

| Компонент | Факты |
|---|---|
| Клиент | `tmdb_adapter/client_singleton.py` — синглтон `TMDbAPIs`, RU и EN инстансы |
| Зависимость | `pyproject.toml`: `tmdbapis` + git-форк `swasher/TMDbAPIs` |
| Read-сценарии | `movie()`, `tv_show()`, `person()`, `tv_season()`, `collection()`, `movie_search()`, `tv_search()`, `find_by_id()` |
| Write-сценарии | watchlist / favorite / rating через методы объектов `Movie`/`TVShow` |
| V4-списки | `tmdb._api4`: `account_get_lists`, `list_create_list`, `list_add_items`, `list_remove_items`, `list_delete_list`, `list_update_list` |
| Auth | `vault/api.py`: start/approve через raw `requests`, logout через `tmdb.logout()` |
| Очистка аккаунта | `clear_tmdb_account.py`: raw requests + fallback на `tmdb._api3/_api4` |
| Масштаб | ~25 вызовов `get_tmdb_client()`, 6 сервисов, ~60 тестовых patch-ей с fake-клиентами |

Ключевая особенность текущего `tmdbapis`: `tmdb.movie(id)` делает **один** запрос с огромным `append_to_response` (`credits`, `external_ids`, `keywords`, `videos`, `alternative_titles` и т.д.) и возвращает уже «полный» объект. `tmdbfusion` так не умеет — это главный источник сложности.

---

## 3. Разрывы `tmdbfusion 0.2.0`

| № | Что нужно проекту | Что есть в `tmdbfusion 0.2.0` | Решение |
|---|---|---|---|
| 1 | Python в проде | `requires-python >= 3.13`, а `Dockerfile` — `python:3.12-slim` | Обновить Docker/CI до 3.13 |
| 2 | V3 API key | `_build_headers(use_bearer=False)` отправляет `Authorization: Bearer <api_key>`. Официально TMDB принимает как Bearer только v4 access token, а v3 key — через `api_key` query-параметр | Либо требовать `tmdb_v4_read_access_token` для чтения, либо патч/форк: добавлять `api_key` в query |
| 3 | `credits`, `keywords`, `videos`, `alternative_titles`, `external_ids` в деталях | В `MovieDetails`/`TVSeriesDetails` этих полей нет; `append_to_response` принимается, но `msgspec` молча отбрасывает неизвестные поля | Один raw-запрос `client._get(..., dict)` с append + маппинг в DTO, либо форк-патч моделей |
| 4 | Эпизоды сезона | `TVSeason` не содержит `episodes` | Raw-запрос `/tv/{id}/season/{n}` в dict, либо форк-патч `TVSeason` |
| 5 | V4 `account_id` для списков | `AccountV4API` требует `account_id`, метода `details()` нет | `GET /4/account` через `client._get(..., version=4)` |
| 6 | Watchlist/favorite/rating | Нет V4 write-методов; V3-методы требуют `session_id` | Лениво создавать V3 session через `authentication.create_session_from_v4(write_token)` и использовать `account.add_to_watchlist/add_favorite`, `movies/tv.add_rating/delete_rating` |
| 7 | Logout | Нет единого `logout()` | `auth_v4.logout(access_token=...)` + `authentication.delete_session(session_id=...)` |
| 8 | Даты, кредиты, страны | `release_date`, `first_air_date`, `birthday`, `deathday` — строки; у кредитов поле `id`, а не `person_id`; страны — `production_countries`/`origin_country`, а не `countries`/`origin_countries` | Явный слой мапперов |
| 9 | Классы ошибок | `TMDBError.status_code` — это **код TMDB** (7, 34...), а HTTP-статус — `http_status` | Переписать `_is_auth_error`/`_is_rate_limited` на типы и `http_status` |
| 10 | Зрелость библиотеки | 0.2.0, один релиз, расхождения README и кода (`mark_as_favorite`, `TMDB()`, `delete_access_token`) | Пиновать точную версию/rev, проверять исходники, а не docs |

---

## 4. Варианты миграции

| Вариант | Суть | Плюсы | Минусы | Оценка |
|---|---|---|---|---|
| **A. Facade** | `tmdb_adapter` эмулирует старый API `tmdbapis` (`movie()`, `_api4`, object-методы) поверх `tmdbfusion` | Сервисы и тесты почти не меняются | Сохраняет legacy-семантику и приватные `_api4`; скрывает библиотеку; плохо для будущего | 2–3 дня |
| **B. Прямая миграция** | Сервисы вызывают `tmdbfusion` напрямую | Чисто и идиоматично | Много правок в 6 сервисах, библиотека протекает во все слои, высокий риск регрессий | 8–12 дней |
| **C. Gateway + DTO** ✅ | `tmdb_adapter/gateway.py` отдаёт доменные DTO; сервисы не знают о `tmdbfusion` | Баланс: минимум изменений логики, библиотека изолирована, тесты стабильны | Нужно написать DTO/мапперы | 7–10 дней |

Рекомендую **вариант C**.

---

## 5. Целевая архитектура

```text
vault/services/*  (matching, sync, import, collection, writeback)
        │
        ▼
tmdb_adapter/gateway.py        ← единственная точка входа
        │
        ├── dto.py / mappers.py  ← нормализация данных
        ├── writeback.py         ← session, watchlist/favorite/rating, V4 lists
        └── client_singleton.py  ← TMDBClient RU/EN, lock, reset, close
        │
        ▼
tmdbfusion.TMDBClient (синхронный, httpx)
```

Новые модули:

| Файл | Ответственность |
|---|---|
| `tmdb_adapter/client_singleton.py` | Создание/пересоздание `TMDBClient` RU/EN, `reset_tmdb_clients()`, закрытие старых клиентов |
| `tmdb_adapter/gateway.py` | `fetch_movie`, `fetch_tv`, `fetch_person`, `fetch_season`, `fetch_collection`, `search_movies`, `search_tv`, `find_by_imdb`, write-методы, `logout` |
| `tmdb_adapter/dto.py` | `TmdbMovie`, `TmdbTv`, `TmdbPerson`, `TmdbCredit`, `TmdbSeason`, `TmdbEpisode`, `TmdbCollection`, `TmdbSearchItem`, `TmdbFindResult` |
| `tmdb_adapter/mappers.py` | Парсинг дат, кредитов, стран, ключевых слов, видео, external_ids |
| `tmdb_adapter/exceptions.py` | Опционально: нормализация ошибок и helper-ы `is_auth_error` / `is_rate_limited` / `is_not_found` |

DTO намеренно повторяют имена полей старого `tmdbapis` (`cast`, `crew`, `countries`, `person_id`, `release_date` уже как `date`), чтобы логика сервисов осталась прежней.

---

## 6. Этапы

### Этап 0. Spike и Go/No-Go — 0.5–1 день

Задачи:
1. Ветка `migration/tmdbfusion`.
2. Одноразовый скрипт (не коммитить) на реальном TMDB:
    - `TMDBClient(api_key=<v3 key>)` → проверить, работает ли чтение (ожидаемо — нет);
    - `TMDBClient(api_key=<v4 read token>)` → чтение v3;
    - `access_token=<write token>` + `create_session_from_v4` → `account.details`, add/remove watchlist, favorite, rating;
    - V4 lists: create/add/remove/update/delete;
    - `language="ru-RU"` и `"en-US"`;
    - замерить число запросов на `fetch_movie`.
3. Проверить установку `tmdbfusion` на Python 3.13 (Windows и Linux/Docker).

Go/No-Go:
- есть рабочий путь auth без потери текущего сценария «только `tmdb_api_key`» **или** согласовано требование v4 read token;
- подтверждён способ получать append-поля и эпизоды;
- Docker на 3.13 собирается.

### Этап 1. Зависимости и Python 3.13 — 0.5 дня

Файлы: `pyproject.toml`, `uv.lock`, `Dockerfile`, возможно `README.md`.

- `requires-python = ">=3.13"`.
- Добавить `tmdbfusion==0.2.0` (или git-rev форка).
- Удалить `tmdbapis` и секцию `[tool.uv.sources]` для него.
- `Dockerfile`: `FROM python:3.13-slim` в builder и runtime.
- `uv lock && uv sync`.
- Проверить сборку `scrapling`, `psycopg`, `rtfox-browser` на 3.13.

Критерий: `uv run python -c "import tmdbfusion"`; `docker build` проходит.

### Этап 2. Адаптер: singleton + DTO + gateway — 1.5–2 дня

Файлы: `tmdb_adapter/client_singleton.py`, новые `gateway.py`, `dto.py`, `mappers.py`.

- Singleton:
    - `api_key = pref.tmdb_v4_read_access_token or pref.tmdb_api_key` (решение по auth из spike);
    - `access_token = pref.tmdb_v4_authenticated_access_token or pref.tmdb_v4_read_access_token`;
    - `language="ru-RU"` / `"en-US"`;
    - `retries=0` (сохраняем текущую семантику; ретраи — на уровне очереди);
    - `cache_ttl=None`;
    - `reset_tmdb_clients()` закрывает старые клиенты.
- DTO и мапперы для movie/tv/person/season/collection/search/find.
- Gateway:
    - детали — один raw-запрос `client._get(path, dict, params={"append_to_response": ...})`;
    - поиск/`find` — публичные методы;
    - write-операции — отдельный модуль/секция.
- Юнит-тесты мапперов: даты, `person_id`, `production_countries`, `keywords`, `videos`, `alternative_titles`, `external_ids`.

Критерий: адаптер отдаёт корректный DTO для фильма 550 и сериала с сезонами; сервисы ещё не тронуты.

### Этап 3. Read-путь — 2–3 дня

Файлы:
- `vault/services/tmdb_movie_matching_service.py`
- `vault/services/tmdb_movie_sync_service.py`
- `vault/services/tmdb_movie_import_service.py`
- `vault/services/collection_service.py`
- `vault/services/tmdb_smart_search_service.py` (косвенно, через `_search_once`)

Что менять:
- `tmdb.movie_search` → `gateway.search_movies`;
- `tmdb.tv_search` → `gateway.search_tv`;
- `tmdb.find_by_id` → `gateway.find_by_imdb`;
- `tmdb.movie` / `tv_show` → `gateway.fetch_movie` / `fetch_tv`;
- `tmdb.person` → `gateway.fetch_person`;
- `tmdb.tv_season` → `gateway.fetch_season`;
- `tmdb.collection` → `gateway.fetch_collection`;
- `_extract_year` в matching — использовать `date` из DTO, а не `.year` у строки;
- `_apply_movie_payload` / `_apply_tv_payload` — даты уже `date`;
- `_sync_countries` — `production_countries` + `origin_country`;
- `_sync_movie_persons` — кредиты из DTO с `person_id`;
- `_apply_keywords`, `videos`, `alternative_titles` — из DTO;
- TV `imdb_id`/`tvdb_id` — из `external_ids`.

Критерий:
- все тесты matching/sync/import/collection зелёные;
- golden-diff на 20 фильмах/10 сериалах не хуже текущего поведения.

### Этап 4. Write-путь — 1.5–2 дня

Файлы:
- `vault/services/tmdb_writeback_service.py`
- `vault/api.py`
- `clear_tmdb_account.py`

Что менять:
- убрать `_get_tmdb_obj()` и методы объектов `add_to_watchlist`, `mark_as_favorite`, `rate`, `delete_rating`;
- gateway: `set_watchlist`, `set_favorite`, `set_rating`;
- V3 session: лениво `create_session_from_v4(write_token)`, кэш `session_id`;
- account id: v3 — `account.details(session_id).id`, v4 — `GET /4/account`;
- `_api4.*` → `lists_v4.*` + `account_v4.lists`;
- `create_list` теперь возвращает `dict` → `result["id"]`;
- logout: `auth_v4.logout` + `authentication.delete_session`;
- `_is_auth_error` — `AuthenticationError`/`AuthorizationError` + `http_status == 401/403`;
- `_is_rate_limited` — `RateLimitError` + `http_status == 429`;
- 404 — `NotFoundError`, а не строковый `"not found"` (сообщение `tmdbfusion` — `"could not be found"`, текущая проверка его не поймает);
- `retries=0` для write-клиента, чтобы встроенный retry не создавал дубликаты списков.

Критерий: ручная матрица write-back проходит полностью (см. §10).

### Этап 5. Тесты, документация, cleanup — 1.5–2 дня

- Заменить fake-клиенты в тестах на `FakeTmdbGateway` (3 файла, ~60 patch-ей).
- Добавить тесты адаптера и классификации ошибок.
- Удалить `tmdbapis` из `uv.lock`, `pyproject.toml`, импортов и комментариев.
- Обновить `docs/WRITEBACK_IMPLEMENTATION.md`, `TODO.md`, `clear_tmdb_account.py` (docstring), при необходимости `AGENTS.md`.
- Финальный `grep -R "tmdbapis"` — только архивные docs.
- Полный прогон: `uv run python manage.py test vault core moviefilter`.

---

## 7. Маппинг вызовов

| Сейчас (`tmdbapis`) | Новый gateway |
|---|---|
| `TMDbAPIs(api_key, v4_access_token=..., language="RU")` | `TMDBClient(api_key=..., access_token=..., language="ru-RU")` |
| `tmdb.configuration()` | `client.configuration.details()` / `sync_config()` |
| `tmdb.movie(id)` | `gateway.fetch_movie(id)` |
| `tmdb.tv_show(id)` | `gateway.fetch_tv(id)` |
| `tmdb.person(id)` | `gateway.fetch_person(id)` |
| `tmdb.tv_season(tv, n)` | `gateway.fetch_season(tv, n)` |
| `tmdb.collection(id)` | `gateway.fetch_collection(id)` |
| `tmdb.movie_search(...)` | `gateway.search_movies(...)` |
| `tmdb.tv_search(...)` | `gateway.search_tv(...)` |
| `tmdb.find_by_id(imdb_id=...)` | `gateway.find_by_imdb(...)` |
| `tmdb.create_list(...)` | `gateway.create_list(...)` |
| `tmdb._api4.account_get_lists(page)` | `gateway.get_account_lists(page)` |
| `tmdb._api4.list_add_items(...)` | `gateway.add_list_items(...)` |
| `tmdb._api4.list_remove_items(...)` | `gateway.remove_list_items(...)` |
| `tmdb._api4.list_delete_list(...)` | `gateway.delete_list(...)` |
| `tmdb._api4.list_update_list(...)` | `gateway.update_list(...)` |
| `movie.add_to_watchlist()` | `gateway.set_watchlist(...)` |
| `movie.mark_as_favorite()` | `gateway.set_favorite(...)` |
| `movie.rate(r)` | `gateway.set_rating(..., r)` |
| `movie.delete_rating()` | `gateway.set_rating(..., None)` |
| `tmdb.logout()` | `gateway.logout()` |
| `tmdb._api4.account_id` | `gateway.get_v4_account_id()` |
| `tmdb._api3.account_id` | `gateway.get_v3_account_id()` |

---

## 8. Нормализация данных

| Поле | `tmdbfusion` | В DTO |
|---|---|---|
| `release_date`, `first_air_date`, `last_air_date`, `air_date` | `str` / `""` | `date \| None` |
| `birthday`, `deathday` | `str \| None` | `date \| None` |
| `original_language` | `str` | `str` |
| кредиты | `CastMember.id`, `CrewMember.id` | `person_id` |
| `created_by` (TV) | `Creator.id`, нет `original_name/popularity/order` | `person_id`, дефолты |
| страны | `production_countries`, `origin_country: list[str]` | `countries`, `origin_countries` |
| keywords | movie `.keywords`, tv `.results` | единый `list[TmdbKeyword]` |
| videos | `.results` | `list[TmdbVideo]` |
| alternative_titles | movie `.titles`, tv `.results` | `list[TmdbAlternativeTitle]` |
| external_ids (TV) | отдельный вызов | `imdb_id`, `tvdb_id` |
| seasons/episodes | `TVSeason` без `episodes` | `TmdbSeason.episodes` из raw dict |

---

## 9. Ошибки, retry и лимиты

Критичные ловушки:

1. `TMDBError.status_code` — код TMDB, не HTTP. Все проверки `status_code == 401/429` заменить на `http_status` или типы.
2. `tmdbfusion` не содержит `"429"` в сообщении и `"not found"` в тексте 404. Строковые проверки в write-back перестанут работать — только типы.
3. Встроенные retry `tmdbfusion` повторяют 429 и 5xx. Для `create_list` это риск дублей. Ставить `retries=0` и полагаться на `TMDBWritebackQueueItem`.
4. `TmdbRateLimiter` оставить: 2 req/s. Встроенный retry не заменяет глобальный лимитер.
5. `cache_ttl` не включать для синка — иначе можно получить устаревшие данные.
6. Один `httpx.Client` на процесс; при смене токена — `close()` и пересоздание.

---

## 10. Тестирование и приёмка

### Автотесты
- Юнит-тесты мапперов: даты, `person_id`, страны, keywords/videos/alternative_titles, external_ids, эпизоды.
- Тесты gateway с mock transport (`respx`) или fake-клиентом.
- Обновлённые тесты matching/sync/import/smart search/collection.
- Тесты классификации ошибок: 401, 403, 404, 429 с `retry_after`.
- Полный прогон: `uv run python manage.py test vault core moviefilter`.

### Golden parity
На dev/test БД:
1. Прогнать `sync_movie(force_rematch=True)` для 20 фильмов и 10 сериалов на старом стеке, сохранить JSON полей и связей.
2. Повторить на новом стеке.
3. Diff: даты, годы, жанры, страны, персоны, сезоны, эпизоды, рейтинги, коллекции.
4. Ожидаемые отличия — только `homepage`/`trailer_url`/порядок персон; всё остальное — баг.

### Ручная матрица write-back
- movie и tv: watchlist add/remove, favorite add/remove, rating 1/10, unrate.
- skip/watched list: add/remove; удалить список на TMDB → триггер → пересоздание.
- пользовательский список: create, rename, add/remove item, delete.
- протухший write token → корректная auth-ошибка и запись в очередь.
- 429 (mock) → `retry_after` и повтор.
- logout → токен очищен, сессия удалена, синглтон сброшен.

### Definition of Done
- [ ] `grep -R "tmdbapis"` по коду пуст.
- [ ] `uv lock` без `tmdbapis`.
- [ ] Все тесты зелёные.
- [ ] Golden parity пройден.
- [ ] Ручная матрица write-back пройдена.
- [ ] Docker на Python 3.13 собирается и запускается.
- [ ] 48 часов без роста ошибок в `logs/error.log` и `vault.tmdb_writeback`.
- [ ] `docs/WRITEBACK_IMPLEMENTATION.md` обновлён.

---

## 11. Риски

| Риск | Вероятность | Влияние | Мера |
|---|---|---|---|
| V3 key не работает как Bearer | Высокая | Высокое | Требовать v4 read token или патч auth |
| Append-поля теряются | Высокая | Высокое | Raw `_get` с append или форк моделей |
| Нет эпизодов в `TVSeason` | Высокая | Высокое | Raw dict для сезона или форк |
| Нет V4 account_id | Высокая | Среднее | `GET /4/account` |
| V3 session не создаётся | Средняя | Высокое | Fallback на raw V4 write endpoints |
| Даты/кредиты/страны ломают синк | Высокая | Среднее | Мапперы + golden parity |
| Ошибки классифицируются неверно | Высокая | Высокое | Типы + `http_status` + тесты |
| Дубли списков из-за retry | Средняя | Высокое | `retries=0` + идемпотентность |
| Молодая библиотека ломает API | Средняя | Высокое | Пиновать точную версию/rev, форк |
| Python 3.13 на проде | Средняя | Высокое | Обновить Docker до начала миграции |
| Больше HTTP-запросов | Средняя | Среднее | Один append-запрос на детали |
| Нет тестов write-back | Высокая | Среднее | Добавить тесты + ручная матрица |

---

## 12. Оценка

| Этап | Дни |
|---|---|
| 0. Spike / Go-No-Go | 0.5–1 |
| 1. Зависимости и Python 3.13 | 0.5 |
| 2. Adapter: singleton, DTO, mappers, gateway | 1.5–2 |
| 3. Read-путь | 2–3 |
| 4. Write-путь | 1.5–2 |
| 5. Тесты, docs, cleanup | 1.5–2 |
| **Итого** | **7.5–10.5** |
| Форк/патчи upstream | +1–2 |

---

## 13. Открытые решения

1. **Форк или private API?**
    - Форк `tmdbfusion` (как сейчас с `TMDbAPIs`) — чище и быстрее, но нужно поддерживать.
    - Без форка — один приватный вызов `client._get(..., dict)` для деталей/сезонов и `GET /4/account`; пиновать версию.

2. **Auth:**
    - требовать `tmdb_v4_read_access_token` для чтения (ломает сценарий «только `tmdb_api_key`»), или
    - патчить `tmdbfusion`, чтобы v3 key уходил в `api_key` query.

3. **Python 3.13 на проде** — обновляем Docker сразу или миграция ждёт обновления инфраструктуры?

4. **Feature flag** — нужен ли временный переключатель `TMDB_BACKEND=legacy|fusion`, или деплоим веткой с откатом через revert?

---

## 14. Рекомендуемый первый шаг

Сделать **Этап 0** и по jego результатам зафиксировать:
- рабочий auth-путь;
- нужен ли форк;
- точный список raw-вызовов.

После этого можно оценивать остаток работ уже по фактическим данным, а не по документации библиотеки (она местами расходится с кодом).