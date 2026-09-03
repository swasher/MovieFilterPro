# Write-back Vault → TMDB — документация по реализации

> **Назначение:** этот документ описывает РАБОТУ системы write-back в том виде,
> в котором она реализована сейчас. Это живой документ: обновляйте его при изменении
> архитектуры. Для истории решений и нюансов см. также
> [`archive/PLAN_TWO_WAY_SYNC.md`](./archive/PLAN_TWO_WAY_SYNC.md) (история плана) и
> [`archive/TMDB-WRITEBACK-IMPROVEMENTS.md`](./archive/TMDB-WRITEBACK-IMPROVEMENTS.md) (закрытые/открытые задачи).

## 1. Что это и зачем

Write-back — это обратная запись пользовательских данных Vault в TMDB:
- статус просмотра → **watchlist** TMDB
- избранное → **favorites** TMDB
- оценка → **rating** TMDB
- системный статус «Не интересует» (SKIP) → отдельный **TMDB-лист «Не интересует»**
- пользовательские списки (`UserList`) → **TMDB Lists** (создание/переименование/удаление/состав)

**Базовый принцип:** записи выполняются **асинхронно через HUEY**. Локальные данные
меняются мгновенно, а TMDB-вызовы ставятся в фоновую очередь. UI не блокируется
HTTP-вызовами к TMDB.

## 2. Поток данных (важно понять до любых правок)

```
Пользователь меняет статус/оценку/список
        │
        ▼
Django ORM .save()/.delete()          (vault/models, MovieStatusService, API)
        │
        ▼
Сигнал (vault/signals.py)             post_save / post_delete / pre_delete
        │
        ├── pre_delete → снапшот данных в модульные dict-кэши (_pending_*_cache)
        │                          (объект ещё жив; после каскадного delete его не восстановить)
        ▼
transaction.on_commit(...)            гарантия, что локальный коммит прошёл
        │
        ▼
TmdbWritebackDispatch.schedule_*(...) (vault/services/tmdb_writeback_dispatch.py)
        │    ставит HUEY-задачу с delay=2, дедупликация через Result.reschedule()
        ▼
HUEY task (vault/tasks.py)            tmdb_writeback_user_movie / _delete / list_*
        │
        ▼
TmdbWritebackService.sync_*(...)      (vault/services/tmdb_writeback_service.py)
        │    guard → TMDB API → WritebackResult
        ▼
При failure → TMDBWritebackQueueItem   (persistent queue, retry_tick раз в 10 мин)
```

## 3. Ключевые файлы

| Файл | Роль | Что делает |
|------|------|------------|
| `vault/signals.py` | Точки входа | Ловит мутации `UserMovie`, `UserListMovie`, `UserList`; снапшоты для удаления; `on_commit`. |
| `vault/services/tmdb_writeback_dispatch.py` | Диспетчер | Единственное место, где сигналы ставят HUEY-задачи. Дедупликация, delay. |
| `vault/tasks.py` | HUEY-задачи | Тонкие обёртки над сервисом: `tmdb_writeback_user_movie`, `_user_movie_delete`, `_list_item_added/removed`, `_list_sync`, `_list_delete`, `tmdb_writeback_retry_tick`, `tmdb_lists_init`. |
| `vault/services/tmdb_writeback_service.py` | Сервис | Вся прикладная логика TMDB-вызовов, guards, persistent queue helpers. |
| `vault/models.py` | Модели | `TMDBWritebackQueueItem`, `UserList.tmdb_list_id`. |
| `vault/constants.py` | Константы | `SKIP_LIST_NAME` и системные label-константы. |
| `moviefilter/models.py` | Preferences | `tmdb_writeback_enabled`, `tmdb_v4_authenticated_access_token`, `tmdb_skip_list_id`, `tmdb_lists_initialized`. |
| `tmdb_adapter/client_singleton.py` | Инфраструктура | `get_tmdb_client()` — единый синглтон `TMDbAPIs`. |
| `vault/api.py` | API | Эндпоинты writeback + ручной push. |

> Границы: **`tmdb_adapter`** — только инфраструктура (клиент, auth). Всю прикладную
> логику writeback держать в `vault/services/tmdb_writeback_service.py`. Мутаторы
> (`MovieStatusService`, `vault/views.py`) не должны знать про TMDB — их покрывают
> сигналы.

## 4. Маппинг данных Vault → TMDB

| Vault | TMDB | Комментарий |
|-------|------|-------------|
| `UserMovie.watch_status == PLAN` | `add_to_watchlist()` | |
| `watch_status == WATCHED/SKIP/None` | `remove_from_watchlist()` | |
| `UserMovie.is_favorite` | `mark/remove_as_favorite()` | |
| `UserMovie.rating` (1–10) | `rate(float)` / `delete_rating()` | TMDB принимает 1–10 (целые валидны) |
| `watch_status == SKIP` | `list_add_items` в TMDB-лист «Не интересует» | ID списка в `prefs.tmdb_skip_list_id` |
| `UserList` create | `list_create_list` → `UserList.tmdb_list_id` | |
| `UserList` rename | `list_update_list` | |
| `UserList` delete | `list_delete_list` | |
| `UserListMovie` add | `list_add_items` | автосоздание листа в `sync_list_item_added` если нет `tmdb_list_id` |
| `UserListMovie` remove | `list_remove_items` | |
| При удалении `UserMovie` | watchlist/favorite/rating remove | cleanup из `sync_user_movie_deleted` |

**Не синхронизируется:** сезоны/эпизоды (`UserSeason`) — TMDB не поддерживает
watchlist/favorite для эпизодов, только рейтинги (отдельная фаза, не реализована).

## 5. Асинхронный конвейер (dispatch + HUEY)

### 5.1 Диспетчер (`tmdb_writeback_dispatch.py`)

- `WRITEBACK_DELAY_SECONDS = 2` — окно дедупликации.
- `TmdbWritebackDispatch._schedule(task, key, args)`:
  - хранит последний `Result` per ключ в `_pending: dict[str, Result]`;
  - при повторном вызове с тем же ключом зовёт `pending.reschedule(delay=...)` —
    Huey отзывает старую scheduled-задачу и ставит новую с теми же аргументами;
  - выполнится только **последняя** версия (3 toggle за 2 сек = 1 запрос).

Публичные методы (вызываются из signals):
`schedule_user_movie_writeback`, `schedule_user_movie_delete`,
`schedule_list_item_added`, `schedule_list_item_removed`, `schedule_list_sync`,
`schedule_list_delete`.

### 5.2 HUEY-задачи (`vault/tasks.py`)

Все обёртки — «тонкие»: загружают объект по id и зовут метод сервиса. Для
delete-задач принимаются **снапшот-данные** (`tmdb_id`, `media_type`), т.к. после
каскадного удаления строки в БД нет.

- `tmdb_writeback_user_movie(user_movie_id)` → `sync_user_movie_to_tmdb_by_id`.
- `tmdb_writeback_user_movie_delete(movie_id, tmdb_id, media_type)` → `sync_user_movie_deleted` (со снапшотом).
- `tmdb_writeback_list_item_added(user_list_movie_id)`.
- `tmdb_writeback_list_item_removed(tmdb_list_id, tmdb_id, media_type)` (снапшот).
- `tmdb_writeback_list_sync(user_list_id)` — create или update листа.
- `tmdb_writeback_list_delete(tmdb_list_id)` (снапшот).
- `tmdb_writeback_retry_tick` — periodic, раз в 10 минут: ретраит pending из `TMDBWritebackQueueItem`.
- `tmdb_lists_init` — обёрнута в `@HUEY.lock_task("tmdb_lists_init")` (статический глобальный лок).

**Важно про Huey 2.6.0:** `lock_task` — статический, per-argument не поддерживает.
Для дедупликации по `user_movie_id` используем `Result.reschedule()`, а не `lock_task`.

## 6. Сервис (`tmdb_writeback_service.py`) — уровни

Файл разделён на Application/ Domain-слои комментариями-шапками:

```
# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #
... guards, queue helpers, готовые обвязки ...

# ------------------------------------ #
#            DOMAIN LAYER              #
# ------------------------------------ #
... sync_watch_status / sync_favorite / sync_rating / sync_skip_list / list_* ...
```

### 6.1 Guards (`_should_writeback`, `_should_writeback_lists`)

- Проверяют: `prefs.tmdb_writeback_enabled`, наличие `tmdb_v4_authenticated_access_token`,
  `movie.tmdb_id`, `movie.tmdb_media_type in ("movie","tv")`.
- Оба принимают опциональный `prefs` (после `_prefs_snapshot()`), чтобы в одном
  `sync_user_movie_to_tmdb` не было нескольких SELECT на `UserPreferences`.
- `_prefs_snapshot()` — единственная точка получения `UserPreferences.get()` в этой операции.

### 6.2 Классификация ошибок

`_is_rate_limited(exc)` — 429.
`_is_auth_error(exc)` — в приоритете типы tmdbapis (`WritePermission`, `PrivateResource`,
`Unauthorized`, `Authentication` из `tmdbapis.exceptions`), плюс `status_code == 401`,
плюс строковый fallback «401»/"Invalid API key"/"Authentication" (для обёрнутых
`Exception(r.error)`).

429 → задача уходит в persistent queue (`state=pending`) и ретраится раз в 10 минут.
401 → задача уходит в persistent queue со `state=error`, без авто-ретрая (нужен re-auth).

### 6.3 Persistent queue (`TMDBWritebackQueueItem`)

- Единственный механизм ретрая failed операций.
- `_upsert_queue_item(movie, error, is_auth=...)` — создаёт/обновляет запись;
  `attempts` инкрементится атомарно через `F("attempts") + 1`.
- `_clear_queue_item(movie)` — удаляет запись при успехе.
- Обрабатывается `tmdb_writeback_retry_tick` (10 мин, лимит 20 за тик).
- UI: страница `/tmdb-writeback` показывает очередь, позволяет Retry/Delete per item.

**Правило:** НЕ добавлять параллельные HUEY-schedule на retry — это давало дубли
запросов (задача #1 была про это). Один источник ретрая = persistent queue.

### 6.4 Публичные методы синхронизации

- `sync_user_movie_to_tmdb(user_movie)` — главный: watch_status + favorite + rating
  + skip_list + custom lists. Собирает `list[WritebackResult]`. В конце — queue handling.
- `sync_user_movie_to_tmdb_by_id(user_movie_id)` — helper для HUEY (select_related('movie')).
- `sync_user_movie_deleted(user_movie)` — cleanup при удалении.
- `sync_watch_status`, `sync_favorite`, `sync_rating` — по одному sub-sync.
- `sync_skip_list(user_movie)` — SKIP ↔ TMDB-лист «Не интересует».
- `sync_list_item_added(list_movie)`, `sync_list_item_removed(list_movie)`.
- `create_tmdb_list`, `update_tmdb_list`, `delete_tmdb_list`.
- `init_all_user_lists()` — инициализация/восстановление всех листов на TMDB.
- `_ensure_skip_list_tmdb_id(prefs=None)` — find-or-create skip list. **Fast-path:**
  если `prefs.tmdb_skip_list_id` заполнен — возвращается напрямую (0 API-вызовов,
  без `list_get_list`). Slow-path (только когда id пуст) — поиск по имени среди
  account lists / создание, под `_skip_list_lock` + `select_for_update` (защита от дублей).

### 6.5 Важные решения в коде (не ломать)

- **Снапшот-кэши в signals** (`_pending_delete_cache`, `_pending_list_delete`)
  **функционально необходимы**: после каскадного удаления строк в БД нет, отложенная
  HUEY-задача получает снапшот только из них (`sync_list_item_removed` требует
  `user_list`/`movie` в памяти). Задача «убрать кэши» (#8) признана не применимой.
- **Автосоздание TMDB-листа** в `sync_list_item_added`: если `user_list.tmdb_list_id`
  пуст — вызывается `create_tmdb_list` (self-heal race между `list_sync` и
  `list_item_added` при async-HUEY). Защита от дублей — `select_for_update`.
- `sync_skip_list` имеет defensive-guard `if not movie_tmdb_id: return None` — он
  валиден (публичный метод), не убирать.
- **Skip-list fast-path (без проверки живости):** `_ensure_skip_list_tmdb_id` НЕ
  вызывает `list_get_list` для кэшированного `tmdb_skip_list_id` в горячем пути.
  Если список удалён на TMDB, `list_add_items`/`list_remove_items` вернёт 404 —
  `sync_skip_list` сбрасывает кэш, пересоздаёт список и повторяет операцию один раз.
  Не возвращать верификацию через `list_get_list` — это лишний API-вызов на фильм.

### 6.6 Оптимизации bulk-синхронизации (10K)

*Архитектура важнее скорости: один фильм — один понятный запрос. Надёжность трассировки
выше экономии на батчинге.*

- **Δ-sync для UserMovie (R1).** Пишется в TMDB только то, что реально изменилось.
  При сохранении определяется дифф по `watch_status / is_favorite / rating`, через
  диспетчер передаётся список изменённых полей, сервис вызывает только нужные
  подсинхронизации. Создание записи — полный синх, отсутствие изменений — пропуск задачи.
  Эффект: смена одного флага = `1` запрос вместо `4–5`. `lists` синхронизируются
  отдельным сигналом `UserListMovie`, а не через `UserMovie`.
- **Отказ от батчинга списков (R2, отмена 2026-09-01).** Один API-вызов на одно
  добавление в список. Батчинг экономит запросы, но при частичном фейле непонятно
  какие фильмы из пачки остались несинхронизированы, требует межпроцессного
  аккумулятора и ломает трассировку.
- **Кэш соответствий пользовательских списков (R3).** Перед массовой операцией
  один раз загружается отображение `UserList → tmdb_list_id` в процесс-локальный
  `dict` и создаётся недостающее на TMDB. Дальше добавления в списки читают из
  памяти, а не из БД. Кэшу достаточно жить пока идёт `bulk-sync` (single-user,
  во время синка других мутаций нет); создание нового списка обновляет кэш.
- **Доверие кэшу без проверки живости (R4).** `init_all_user_lists` не проверяет
  каждый `tmdb_list_id` через `list_get_list` (`100` списков = `0` запросов вместо
  `100`). Живость проверяется лениво: если при реальном `list_add/remove` TMDB
  вернёт `404` — локальный `tmdb_list_id` сбрасывается, список пересоздаётся и
  операция повторяется один раз (тот же паттерн, что у skip-листа).

## 7. Сигналы (`vault/signals.py`)

- `UserMovie post_save` → `schedule_user_movie_writeback(pk)` в `on_commit`.
- `UserMovie pre_delete` → снапшот `(movie_id, tmdb_id, media_type)` в `_pending_delete_cache`.
- `UserMovie post_delete` → `schedule_user_movie_delete(...)` (из кэша/instance) в `on_commit`.
- `UserListMovie post_save` (created) → `schedule_list_item_added(pk)`.
- `UserListMovie pre_delete` → снапшот instance в `_pending_list_delete`.
- `UserListMovie post_delete` → `schedule_list_item_removed(tmdb_list_id, tmdb_id, media_type)`.
- `UserList post_save` → `schedule_list_sync(ul_id)` (skip-лист «Не интересует» пропускается).
- `UserList post_delete` → `schedule_list_delete(tmdb_list_id)`.

Все обёрнуты в `transaction.on_commit` с захватом `pk=pk` по значению (R1-паттерн).
Сигналы НЕ вызывают сервис напрямую — только dispatch.

## 8. API-эндпоинты (`/api/vault/`)

| Метод/путь | Назначение |
|------------|------------|
| `POST /movies/{slug}/tmdb-writeback` | Ручной синхронный push для одного фильма (отдаёт `list[WritebackResult]`). |
| `GET /tmdb-writeback/status` | Статистика (enabled, token present, total_user_movies, with/without tmdb). |
| `PATCH /tmdb-writeback/settings` | Включить/выключить writeback; `tmdb_writeback_lists_enabled` follows main toggle. |
| `GET /tmdb-writeback/queue` | Список persistent queue (последние 200). |
| `DELETE /tmdb-writeback/queue/{item_id}` | Удалить элемент очереди. |
| `POST /tmdb-writeback/queue/{item_id}/retry` | Ручной retry из очереди. |

> `fetch-tmdb`/`fetch-tmdb-confirm` (read-sync) после успешного статуса также зовут
> `sync_user_movie_to_tmdb` синхронно (явное действие пользователя, §20.1 плана).

## 9. Frontend

- `front/src/routes/tmdb-writeback/+page.svelte` — очередь writeback (Retry/Delete).
- `front/src/routes/preferences/+page.svelte` — toggle writeback + ссылка на очередь.
- `front/src/routes/(vault)/movies/[slug]/+page.svelte` — кнопка «Push to TMDB»,
  badge статуса из `movie.writeback` (см. `get_writeback_status`).

## 10. Типовые задачи и где их решать

| Задача | Где править |
|--------|-------------|
| Добавить новое поле в синхронизацию UserMovie | `sync_user_movie_to_tmdb` + новый `sync_*` субсинк |
| Изменить поведение при 429/401 | `_is_rate_limited`/`_is_auth_error`, `_upsert_queue_item` |
| Новая операция над списком | `sync_list_item_*` + HUEY task + dispatch метод + signal |
| Проверить «почему фильм не синхронизировался» | persistent queue + логи `vault.tmdb_writeback` (`logs/debug.log`) |
| Изменить delay дедупликации | `WRITEBACK_DELAY_SECONDS` в dispatch |
| Доработать очередь/статус UI | `/tmdb-writeback/status`+`queue` API и svelte-страницы |

## 11. Проверка после изменений

```bash
uv run python manage.py check
# при изменении моделей:
uv run python manage.py makemigrations && uv run python manage.py migrate
```

Ручной смоук-тест: смени «Буду смотреть» на фильме с `tmdb_id` → в
`logs/debug.log` через 2–3 сек появится `writeback watchlist_add`, на TMDB фильм
попадёт в watchlist. Быстрые повторные переключения → 1 запрос (дедуп).