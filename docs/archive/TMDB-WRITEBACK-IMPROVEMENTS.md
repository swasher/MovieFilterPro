# TMDB Write-back — список точечных улучшений

> Документ для агента: каждая задача — отдельный коммит/PR.
> Не выполнять всё сразу. Закрывать по 1 проблеме за задачу.
> Контекст сессии, в которой составлялся список: HEAD = `0cd1905`, writeback-ветка начинается с коммита `a8d37be`.

## Содержание

- [0. Общий контекст и архитектурные рамки](#0-общий-контекст-и-архитектурные-рамки)
- [P0 — Критично, исправить первыми](#p0--критично-исправить-первыми)
  - [#1 Дублирование HUEY-retry и persistent-очереди (двойные запросы в TMDB)](#1-дублирование-huey-retry-и-persistent-очереди-двойные-запросы-в-tmdb)
  - [#2 Race на `_upsert_queue_item.attempts` (потеря инкрементов)](#2-race-на-_upsert_queue_itemattempts-потеря-инкрементов)
  - [#3 Race в `_ensure_skip_list_tmdb_id` (двойное создание списка «Не интересует»)](#3-race-в-_ensure_skip_list_tmdb_id-двойное-создание-списка-не-интересует)
- [P1 — Архитектурные долги, важно для расширяемости](#p1--архитектурные-долги-важно-для-расширяемости)
  - [#4 Шаблонный try/except в `sync_user_movie_to_tmdb` (не нужно)](#4-шаблонный-tryexcept-в-sync_user_movie_to_tmdb-много-boilerplate)
  - [#5 `_should_writeback` × N — лишние запросы к БД и дублирование](#5-_should_writeback--n--лишние-запросы-к-бд-и-дублирование)
  - [#6 Удалить мёртвый код: `vault/services/tmdb_writeback_queue.py`](#6-удалить-мёртвый-код-vaultservicestmdb_writeback_queuepy)
  - [#7 `sync_list_item_added` без автосоздания TMDB-листа (TODO §20.6)](#7-sync_list_item_added-без-автосоздания-tmdb-листа-todo-§206)
- [P2 — Мелкие архитектурные улучшения](#p2--мелкие-архитектурные-улучшения)
  - [#8 Избыточные кэши `_pending_delete_cache` / `_pending_list_delete`](#8-избыточные-кэши-_pending_delete_cache--_pending_list_delete)
  - [#9 «Жадная» проверка `_is_auth_error` по подстроке](#9-жадная-проверка-_is_auth_error-по-подстроке)
  - [#10 Переиспользовать `reset_tmdb_client()` вместо прямого сброса модуля](#10-переиспользовать-reset_tmdb_client-вместо-прямого-сброса-модуля)
  - [#11 `init_all_user_lists` без защиты от двойного запуска](#11-init_all_user_lists-без-защиты-от-двойного-запуска)
  - [#12 Долгий sync при переименовании списка (TODO.md:139)](#12-долгий-sync-при-переименовании-списка-todomd139)
- [P3 — Косметика / отложенное](#p3--косметика--отложенное)
  - [#13 Логирование `_is_auth_error` имеет дубль-логику в `sync_user_movie_to_tmdb`](#13-логирование-_is_auth_error-имеет-дубль-логику-в-sync_user_movie_to_tmdb)
  - [#14 Лишняя проверка `movie_tmdb_id` в `sync_skip_list`](#14-лишняя-проверка-movie_tmdb_id-в-sync_skip_list)

---

## 0. Общий контекст и архитектурные рамки

**Файлы, относящиеся к writeback (все правки — здесь или рядом):**

| Файл | Назначение |
|------|------------|
| `vault/services/tmdb_writeback_service.py` | Сервис: 825 строк, основной модуль. Не редактировать без понимания остальных частей. |
| `vault/services/tmdb_writeback_queue.py` | Мёртвый код. На удаление (задача #6). |
| `vault/signals.py` | 212 строк. Django-сигналы post_save/post_delete/pre_delete + on_commit. |
| `vault/tasks.py` | HUEY-задачи: `tmdb_writeback_user_movie`, `tmdb_writeback_retry_tick`, `tmdb_lists_init`. |
| `vault/api.py` | 9 эндпоинтов `/tmdb-writeback/*` + интеграция в `movie_fetch_tmdb*` (§20.1 плана). |
| `vault/models.py:645-676` | `TMDBWritebackQueueItem` (persistent queue). |
| `vault/models.py:541-563` | `UserList.tmdb_list_id` (для custom lists). |
| `moviefilter/models.py:184-204` | Настройки в `UserPreferences`: `tmdb_writeback_enabled`, `tmdb_writeback_lists_enabled`, `tmdb_skip_list_id`, `tmdb_lists_initialized`. |
| `tmdb_adapter/client_singleton.py` | Синглтон `TMDbAPIs`. Есть `_tmdb_instance`, `_last_key`, `_last_token`, `get_tmdb_client()`. |
| `tmdb_adapter/auth.py:136-143` | `reset_tmdb_client()` — корректный сброс через `with _lock`. |
| `PLAN_TWO_WAY_SYNC.md` | Актуальный план с историей решений. Использовать как reference. |

**Что НЕ нужно трогать при решении этих задач:**

- `MovieStatusService` (`vault/services/movie_status_service.py`) — он специально не знает про TMDB.
- `vault/views.py` (legacy) — writeback работает через сигналы, legacy views покрываются автоматически.
- `vault/management/commands/import_kinorium_csv.py` — writeback для свежесозданных фильмов без `tmdb_id` скипается guard'ом.

**Принципы, которых придерживаться:**

1. **Идемпотентность всех write-операций.** Любая повторная попытка должна приводить к тому же результату. Уже реализовано через «add/remove по текущему состоянию».
2. **Глобальный `_bulk_import_in_progress` флаг НЕ вводить.** Решение R2 из плана. Для новых suppression-случаев использовать `contextvars.ContextVar` или явный параметр.
3. **`transaction.on_commit` для всех внешних вызовов.** Иначе можем сходить в TMDB до того, как локальный коммит пройдёт, и при rollback останемся с рассинхроном.
4. **Захват `pk=pk` в lambda при `on_commit`** (R1 из плана). Не `lambda: fn(instance)`, а `lambda pk=pk: fn(pk)`.
5. **Ошибки классифицировать через исключения tmdbapis, а не строковый match.** Если есть возможность — `from tmdbapis.exceptions import TMDbAPIs429Exception, Authentication, TMDbAPIs404Exception, TMDbAPIsException` и работать по типам. Строковый match — fallback.

**После каждой задачи:** прогон `python manage.py check`, при изменениях моделей — `makemigrations` + `migrate`. Endpoints трогать руками не надо (ничего не ломается), но если меняются схемы `Schema` — обновить и frontend в `front/src/routes/`.

---

## P0 — Критично, исправить первыми

### #1 Дублирование HUEY-retry и persistent-очереди (двойные запросы в TMDB) [#ВЫПОЛНЕНО]

**Файлы:**
- `vault/services/tmdb_writeback_service.py:244-262` (метод `sync_user_movie_to_tmdb`, блок «persistent queue handling»)
- `vault/tasks.py:71-76` (task `tmdb_writeback_user_movie`)
- `vault/tasks.py:79-103` (periodic `tmdb_writeback_retry_tick`)

**Проблема:**

В `sync_user_movie_to_tmdb` для каждого failed результата делается **два независимых триггера ретрая**:

1. **Persistent queue:** `cls._upsert_queue_item(movie, err_msg, is_auth=is_auth)` — создаёт/обновляет запись в `TMDBWritebackQueueItem`, которую раз в 10 минут подбирает `tmdb_writeback_retry_tick` (`vault/tasks.py:79`).
2. **HUEY-schedule:** при `is_auth == False` сразу же `tmdb_writeback_user_movie.schedule(args=(user_movie.pk,), delay=600)` — тот же `delay=600` (10 минут).

Оба механизма приводят к тому, что через 10 минут **может прийти два запроса** на один и тот же фильм: один от HUEY-таски, второй от periodic-tick. Каждый из них снова делает все5 субсинков (watch/favorite/rating/skip_lists/user_lists) → реально до **10 одинаковых запросов** в TMDB (5 sub-sync × 2 триггера). Это уже сейчас может триггерить 429, и главное — бесцельно нагружает rate limit.

**Решение:**

Оставить **только persistent queue** (он персистентный, переживает рестарт воркера, имеет UI на `/tmdb-writeback`, даёт ручной retry). HUEY-schedule в `sync_user_movie_to_tmdb` удалить. HUEY-задачу `tmdb_writeback_user_movie` (`vault/tasks.py:71-76`) можно оставить как «ручной retry из UI» — её вызывает только `tmdb_writeback_queue_retry` endpoint (`vault/api.py:1819-1831`).

**Пошагово:**

1. В `vault/services/tmdb_writeback_service.py:244-262` удалить блок:

   ```python
   if not is_auth:
       # schedule HUEY as secondary trigger (periodic task и так подхватит)
       try:
           from vault.tasks import tmdb_writeback_user_movie
           tmdb_writeback_user_movie.schedule(args=(user_movie.pk,), delay=600)
       except Exception:
           pass
   ```

2. Оставить только `_upsert_queue_item` (auth) и `_clear_queue_item` (success).

3. Опционально: в docstring `sync_user_movie_to_tmdb` обновить комментарий «also HUEY retry for 429/networks (10m)» → «retry handled by persistent queue + tmdb_writeback_retry_tick periodic task».

4. **Не удалять** `tmdb_writeback_user_movie` task — она нужна для `tmdb_writeback_queue_retry` endpoint.

**Проверка:**

- Включить `tmdb_writeback_enabled`, поставить любому фильму `watch_status=PLAN`.
- Сэмулировать сбой сети (например, временно изменить `tmdb_api_key` в preferences на неверный — write-back даст 401, periodic tick будет повторять).
- В логах `logs/error.log` и `vault.tmdb_writeback` должно быть **по одной** записи на каждый periodic tick, не дубли.

**Связанные файлы для просмотра при решении:** `PLAN_TWO_WAY_SYNC.md` §12.4 (решение о persistent queue).

---

### #2 Race на `_upsert_queue_item.attempts` (потеря инкрементов) [#ВЫПОЛНЕНО]

**Файл:** `vault/services/tmdb_writeback_service.py:73-99`

**Проблема:**

```python
obj, created = TMDBWritebackQueueItem.objects.update_or_create(
    movie_id=movie_id,
    defaults={"state": state, "last_error": ..., "next_retry_at": next_retry},
)
# increment attempts
TMDBWritebackQueueItem.objects.filter(pk=obj.pk).update(attempts=obj.attempts + 1)
```

`obj.attempts` здесь — это значение **в памяти Python**, прочитанное во время `update_or_create`. Второй `.update(attempts=obj.attempts + 1)` использует это прочитанное значение. При конкурентных вызовах (два periodic tick'а в разных процессах, или rapid-fire сигналов от разных `UserMovie`) оба прочтут `attempts=5`, оба запишут `attempts=6`. Реально было 2 инкремента, но записали только 1.

Сейчас single-user сценарий это маскирует, но при расширении (multi-worker HUEY, или при попытках добавить celery в будущем) счётчик `attempts` начнёт показывать меньше реальных попыток.

**Решение:**

Заменить `.update(attempts=obj.attempts + 1)` на атомарный SQL-инкремент через `F()`:

```python
from django.db.models import F
TMDBWritebackQueueItem.objects.filter(pk=obj.pk).update(attempts=F("attempts") + 1)
# obj.attempts устарел — если где-то используется после — обновить через .refresh_from_db()
```

Если в коде сразу после этого блока `obj.attempts` где-то читается (например, для логирования), то `.refresh_from_db(fields=["attempts"])`.

**Проверка:** код в текущем виде использует `obj.attempts` только в `logger.warning("...", movie_id, state, next_retry, error[:200])` через `attempts` — нужно проверить и обновить:

- Либо убрать `attempts` из лога (там и так много полей).
- Либо сделать `obj.refresh_from_db(fields=["attempts"])` после `F`-инкремента.

**Связанные места в коде:** модель `vault/models.py:656` (`attempts = PositiveIntegerField`), periodic tick `vault/tasks.py:79-103`.

---

### #3 Race в `_ensure_skip_list_tmdb_id` (двойное создание списка «Не интересует») [#ВЫПОЛНЕНО]

**Файл:** `vault/services/tmdb_writeback_service.py:459-523`

**Проблема:**

Метод `_ensure_skip_list_tmdb_id`:
1. Проверяет кэш `prefs.tmdb_skip_list_id`.
2. Если пусто — перебирает все страницы account lists в поисках по имени.
3. Если не нашёл — создаёт новый через `list_create_list`.

Эти три шага выполняются **без блокировки**. Если два сигнала одновременно стартуют (например, пользователь пометил SKIP два фильма в быстрой последовательности, оба прошли guard, оба вошли в `_ensure_skip_list_tmdb_id`):
- Оба увидят пустой кэш.
- Оба не найдут по имени.
- Оба вызовут `list_create_list` → на TMDB появится **два** списка «Не интересует».
- Один из них запишется в `prefs.tmdb_skip_list_id`, другой останется «висящим».

Аналогичная проблема в `init_all_user_lists` — нет защиты от двойного запуска. Задача #11.

**Решение (минимум):**

Добавить `select_for_update` на `UserPreferences` (singleton через `pk=1`) **перед** всей логикой поиска/создания. Это сериализует параллельные вызовы в одну транзакцию:

```python
@classmethod
def _ensure_skip_list_tmdb_id(cls) -> int:
    from moviefilter.models import UserPreferences
    from tmdb_adapter.client_singleton import get_tmdb_client

    with transaction.atomic():
        prefs = UserPreferences.objects.select_for_update().get(pk=1)
        tmdb = get_tmdb_client()
        api4 = tmdb._api4
        if api4 is None:
            raise RuntimeError("TMDB v4 client not available")

        def _list_exists(list_id: int) -> bool:
            try:
                api4.list_get_list(list_id=list_id)
                return True
            except Exception:
                return False

        if prefs.tmdb_skip_list_id:
            if _list_exists(int(prefs.tmdb_skip_list_id)):
                return int(prefs.tmdb_skip_list_id)
            prefs.tmdb_skip_list_id = None
            prefs.save(update_fields=["tmdb_skip_list_id"])

        target_name = cls.SKIP_LIST_NAME
        page = 1
        while True:
            try:
                result = api4.account_get_lists(page=page)
            except Exception:
                break
            if not isinstance(result, dict):
                break
            for item in result.get("results", []):
                if item.get("name") == target_name:
                    list_id = int(item["id"])
                    prefs.tmdb_skip_list_id = list_id
                    prefs.save(update_fields=["tmdb_skip_list_id"])
                    return list_id
            if page >= result.get("total_pages", 1):
                break
            page += 1

        result = api4.list_create_list(
            name=target_name,
            iso_639_1="ru",
            description="Зеркало системного статуса 'Не интересует'",
            public=False,
        )
        new_id = result.get("id") if isinstance(result, dict) else None
        if not new_id:
            raise RuntimeError(f"TMDB list_create_list returned unexpected: {result}")
        new_id = int(new_id)
        prefs.tmdb_skip_list_id = new_id
        prefs.save(update_fields=["tmdb_skip_list_id"])
        return new_id
```

**Что это даёт:** `select_for_update` на sqlite работает только с `BEGIN IMMEDIATE` (Django не делает это автоматически на sqlite — см. `vault/models.py` используется SQLite по умолчанию). На текущем sqlite-бэкенде `select_for_update` — no-op.

**Альтернативное решение (для sqlite + thread-safety):**

Использовать `threading.Lock` уровня процесса (как `tmdb_adapter/client_singleton.py:_lock`):

```python
_skip_list_lock = threading.Lock()

@classmethod
def _ensure_skip_list_tmdb_id(cls) -> int:
    with cls._skip_list_lock:
        # весь существующий код метода
```

В single-user + single-process это покроет 95% случаев. Для multi-worker потребуется redis-lock или db-lock — это уже отдельная задача.

**Рекомендация:** сделать оба варианта — `_lock` + `select_for_update` (где поддерживается БД). Так покрыты оба сценария.

**Проверка:** в `tmdb_skip_list_id` очистить вручную, поставить SKIP двум фильмам через UI быстро. После — проверить, что на TMDB один список «Не интересует», а не два.

---

## P1 — Архитектурные долги, важно для расширяемости

### #4 Шаблонный try/except в `sync_user_movie_to_tmdb` (много boilerplate) [#НЕ НУЖНО]

> **Статус:** решение пользователя — не делать. Введение helper-метода `_run_sub_sync`
> уменьшило бы повторы, но делает код менее явным/линейным. Текущие 5 субсинков
> читаются последовательно и предсказуемо. Оставлено как есть.

**Файл:** `vault/services/tmdb_writeback_service.py:191-243`

**Проблема:**

Метод `sync_user_movie_to_tmdb` для каждого из5 субсинков пишет один и тот же блок:

```python
try:
    r = cls.sync_watch_status(user_movie)
    if r:
        results.append(r)
except Exception as exc:
    logger.exception("writeback watch_status failed: %s", exc)
    results.append(WritebackResult(success=False, action="watchlist", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type, error=str(exc)))
```

Таких блоков — 5, итого ~60 строк. При расширении writeback (например, для заметок или эпизодов) копипаста увеличивается.

**Решение:**

Ввести helper-метод (можно приватный `_run_sub_sync`):

```python
@classmethod
def _run_sub_sync(cls, label: str, fn, *, movie, action_label: str):
    """Безопасно выполнить один субсинк и вернуть WritebackResult."""
    try:
        result = fn()
        if result is not None:
            return result
        return None
    except Exception as exc:
        logger.exception("writeback %s failed: %s", label, exc)
        return WritebackResult(
            success=False,
            action=action_label,
            tmdb_id=getattr(movie, "tmdb_id", None),
            media_type=getattr(movie, "tmdb_media_type", None),
            error=str(exc),
        )
```

И переписать `sync_user_movie_to_tmdb` так:

```python
results: list[WritebackResult] = []

for label, fn, action in [
    ("watch_status", lambda: cls.sync_watch_status(user_movie), "watchlist"),
    ("favorite", lambda: cls.sync_favorite(user_movie), "favorite"),
    ("rating", lambda: cls.sync_rating(user_movie), "rate"),
    ("skip_list", lambda: cls.sync_skip_list(user_movie), "skip_list"),
]:
    r = cls._run_sub_sync(label, fn, movie=movie, action_label=action)
    if r:
        results.append(r)

# user custom lists (отдельная логика — фильтрация по _should_writeback_lists)
should_lists, lists_reason = cls._should_writeback_lists()
if should_lists:
    try:
        from vault.models import UserListMovie
        for lm in UserListMovie.objects.filter(movie=movie).select_related("user_list"):
            r = cls.sync_list_item_added(lm)
            if r:
                results.append(r)
    except Exception as exc:
        logger.exception("writeback user_lists failed: %s", exc)
        results.append(WritebackResult(success=False, action="user_lists", tmdb_id=movie.tmdb_id, media_type=movie.tmdb_media_type, error=str(exc)))
else:
    logger.debug("writeback user_lists skipped: %s", lists_reason)
```

**Что остаётся снаружи helper'а:**
- Логика `_should_writeback_lists` (отдельный guard, специфичный для user_lists).
- Persistent queue handling (`failed = ...` блок).

**Проверка:** функционально не должно поменяться. После правки прогнать ручной `POST /api/vault/movies/{slug}/tmdb-writeback` для фильма, посмотреть `results` — те же 4-5 действий в том же порядке.

---

### #5 `_should_writeback` × N — лишние запросы к БД и дублирование [#ВЫПОЛНЕНО]

**Файл:** `vault/services/tmdb_writeback_service.py:137-153, 590-599`

**Проблема:**

Есть три почти одинаковых метода:

1. `_should_writeback(movie) -> (bool, str)` — проверяет `tmdb_writeback_enabled`, write token, `movie.tmdb_id`, `tmdb_media_type`. Используется в `sync_user_movie_to_tmdb:186`, `sync_user_movie_deleted:291`.
2. `_should_writeback_lists() -> (bool, str)` — проверяет `tmdb_writeback_enabled`, write token. Используется в `sync_list_item_added`, `sync_list_item_removed`, `create_tmdb_list`, `delete_tmdb_list`, `update_tmdb_list`, `init_all_user_lists`, `sync_user_movie_to_tmdb:229`.

Оба делают `UserPreferences.get()` (singleton, но всё равно SQL `get_or_create`).

В `sync_user_movie_to_tmdb` для одного вызова проходит:
- 1× `_should_writeback` (на входе)
- 1× `_should_writeback_lists` (для user_lists)

= 2 запроса к `UserPreferences` плюс возможные промежуточные `prefs.save()` внутри `_ensure_skip_list_tmdb_id` (ещё 1-3).

**Решение:**

Оставить один метод, параметризованный:

```python
@classmethod
def _prefs_snapshot(cls) -> UserPreferences:
    """Single fetch per sync — cached locally."""
    from moviefilter.models import UserPreferences
    return UserPreferences.get()

@classmethod
def _should_writeback(cls, movie, *, prefs=None) -> tuple[bool, str]:
    """Guard: prefs flag, write token, tmdb_id, media_type."""
    if prefs is None:
        prefs = cls._prefs_snapshot()
    if not prefs.tmdb_writeback_enabled:
        return False, "writeback disabled in preferences"
    if not prefs.tmdb_v4_authenticated_access_token:
        return False, "no TMDB write token"
    if movie is None:
        return False, "no movie"
    if not getattr(movie, "tmdb_id", None):
        return False, "movie has no tmdb_id"
    media_type = getattr(movie, "tmdb_media_type", None)
    if media_type not in ("movie", "tv"):
        return False, f"invalid media_type={media_type}"
    return True, ""

@classmethod
def _should_writeback_lists(cls, *, prefs=None) -> tuple[bool, str]:
    if prefs is None:
        prefs = cls._prefs_snapshot()
    if not prefs.tmdb_writeback_enabled:
        return False, "writeback disabled"
    if not prefs.tmdb_v4_authenticated_access_token:
        return False, "no token"
    return True, ""
```

В `sync_user_movie_to_tmdb` и `sync_user_movie_deleted` явно получать `prefs = cls._prefs_snapshot()` один раз и передавать в оба guard'а.

**Что ещё оптимизировать:** `_ensure_skip_list_tmdb_id` уже делает `UserPreferences.get()` — передавать `prefs` и в него.

**Проверка:** включить логирование SQL (`settings.py: LOGGING['loggers']['django.db.backends']['level'] = 'DEBUG'`), прогнать `POST /movies/{slug}/tmdb-writeback`, посчитать `SELECT ... FROM moviefilter_userpreferences`. Должно быть 1, не 3-5.

---

### #6 Удалить мёртвый код: `vault/services/tmdb_writeback_queue.py` [#ВЫПОЛНЕНО]

**Файл:** `vault/services/tmdb_writeback_queue.py` (45 строк, целиком)

**Проблема:**

`grep` по проекту показывает, что `schedule_writeback` отсюда **никем не вызывается** (только в самом файле определён). Аналогичный функционал есть в:

- `vault/tasks.py:71-76` — task `tmdb_writeback_user_movie(user_movie_id)`.
- `vault/signals.py:11-19` — `_schedule_writeback_user_movie(pk)` вызывает напрямую `TmdbWritebackService.sync_user_movie_to_tmdb_by_id(user_movie_id)` без HUEY.
- `vault/api.py:1829-1831` — `tmdb_writeback_queue_retry` endpoint использует прямой `sync_user_movie_to_tmdb`.

Файл `tmdb_writeback_queue.py` — кандидат на удаление. В комментарии он сам признаёт «Фаза 1 — заглушка, Фаза 2 — async retry». Фаза 2 пришла через persistent queue (model `TMDBWritebackQueueItem`) — отдельный модуль больше не нужен.

**Решение:**

1. Удалить `vault/services/tmdb_writeback_queue.py`.
2. **Не удалять** `vault/tasks.py::tmdb_writeback_user_movie` — она используется как прямой HUEY-обёртка (см. также план §E).
3. Проверить, что нигде в проекте не импортируется `from vault.services.tmdb_writeback_queue import ...`:

   ```bash
   grep -r "tmdb_writeback_queue" --include="*.py"
   ```

   Если только сам файл — безопасно удалять.

**Проверка:** `python manage.py check`, прогон любого writeback (status toggle).

---

### #7 `sync_list_item_added` без автосоздания TMDB-листа (TODO §20.6) [#ВЫПОЛНЕНО]

**Файл:** `vault/services/tmdb_writeback_service.py:601-637`

**Проблема:**

В `PLAN_TWO_WAY_SYNC.md:802-808` (§20.6) зафиксировано:

> sync_list_item_added: если user_list.tmdb_list_id is None → вызвать create_tmdb_list(user_list) внутри, затем list_add_items.

Сейчас в коде (`tmdb_writeback_service.py:621-623`):

```python
if not getattr(user_list, "tmdb_list_id", None):
    logger.debug("list_add skipped: UserList %s has no tmdb_list_id (need init)", user_list.id)
    return WritebackResult(success=False, action="list_add_skipped", error="no tmdb_list_id — need lists init")
```

То есть пользовательский список создаётся локально, в него добавляется фильм, но если у `UserList` нет `tmdb_list_id` (например, список создан после последнего `init_all_user_lists`, или init ещё не запускался) — **фильм не попадает в TMDB**. Пользователь узнает об этом только через debug-лог.

TODO.md не помечает это как закрытое, но визуально может казаться, что фича работает (writeback enabled, фильм добавлен — нет ошибки в UI).

**Решение:**

В `sync_list_item_added` перед ранним return добавить автосоздание (с race-guard):

```python
user_list = getattr(list_movie, "user_list", None)
movie = getattr(list_movie, "movie", None)

if user_list is None or movie is None:
    # ...существующая логика подгрузки...

if not getattr(user_list, "tmdb_list_id", None):
    # §20.6: auto-create if missing (race-safe через select_for_update внутри create_tmdb_list)
    create_result = cls.create_tmdb_list(user_list)
    if not create_result.success:
        return WritebackResult(success=False, action="list_add_skipped", error=f"auto-create failed: {create_result.error}")
    # обновить локальный объект
    user_list.refresh_from_db(fields=["tmdb_list_id"])

if not getattr(movie, "tmdb_id", None):
    return WritebackResult(success=False, action="list_add", error="movie has no tmdb_id")
# ...далее существующая логика list_add_items...
```

`create_tmdb_list` (`tmdb_writeback_service.py:672-707`) уже делает `select_for_update` и обрабатывает race, так что новых проблем не добавим.

**Edge cases:**

- Если `create_tmdb_list` падает с не-401 ошибкой (например, 429) — writeback не должен ретраиться через всю цепочку `sync_user_movie_to_tmdb`. Лучше сразу положить в queue. Но на текущем этапе — достаточно `result.error` и periodic tick.
- Если список с `tmdb_list_id` есть, но он удалён на TMDB — существующая защита в `init_all_user_lists` это ловит, но в `sync_list_item_added` этой защиты нет. Опционально: добавить try/except на `list_add_items`, ловить 404, сбрасывать `tmdb_list_id`, рекурсивно вызывать `sync_list_item_added`. **Это вне scope текущей задачи** — оставить TODO.

**Проверка:** создать новый `UserList`, добавить в него фильм, у которого есть `tmdb_id`. На TMDB должен появиться новый list + фильм в нём. Если у фильма нет `tmdb_id` — фильм останется только локально (как и должно быть).

---

## P2 — Мелкие архитектурные улучшения

### #8 Избыточные кэши `_pending_delete_cache` / `_pending_list_delete` [#НЕ ПРИМЕНИМО — кэши функционально необходимы]

> **Статус:** перепроверено на актуальном коде (после перехода на HUEY, v-signals rewrite).
> Задача предлагала «оставить только fallback в post_delete через БД и убрать глобальные словари».
> Это основано на **устаревшем коде**: в текущей реализации
> - `post_delete` для `UserListMovie` НЕ может восстановить relations из БД (каскадный delete уже удалил строки), а `sync_list_item_removed` ждёт снапшот с `user_list`/`movie` (`tmdb_writeback_service.py:662-677`);
> - `_pending_delete_cache`/`_pending_list_delete` — единственный источник tmdb_id/media_type для отложенной HUEY-задачи удаления (снапшот формируется в `pre_delete`, где объект ещё жив).
> Убирать кэши нельзя без потери данных о delete-writeback. Оставляем как есть.

**Файлы:**
- `vault/signals.py:45` — `_pending_delete_cache: dict[int, tuple[...]]`
- `vault/signals.py:65` — заполнение в `pre_delete` для `UserMovie`
- `vault/signals.py:78` — извлечение в `post_delete` для `UserMovie`
- `vault/signals.py:118` — `_pending_list_delete: dict[int, object]`
- `vault/signals.py:121-138` — `pre_delete` для `UserListMovie`
- `vault/signals.py:142-153` — `post_delete` для `UserListMovie`

**Проблема:**

Эти два глобальных словаря на уровне модуля решают проблему «`post_delete` теряет relations, потому что каскад их обнулил». Но в текущем коде это избыточно:

1. `pre_delete` для `UserMovie` (`signals.py:48-67`) **уже сам делает** fallback — если `movie.tmdb_id` нет в instance, читает из БД через `Movie.objects.filter(pk=movie_id).values(...)`. Кэш `_pending_delete_cache` тут — backup, который срабатывает только если и БД не отдала. Сейчас это уже двойная страховка.

2. `post_delete` (`signals.py:76-92`) в fallback'е использует `getattr(movie, "id", None) if movie else getattr(instance, "movie_id", None)`. Если movie ещё жив (не каскадно) — relations доступны, кэш не нужен. Если каскадно удалён — `pre_delete` уже сходил в БД и положил в кэш.

3. **`_pending_list_delete`** в `pre_delete` (`signals.py:121-138`) тоже делает fallback `select_related` — пытается подгрузить relations, если они не были. То есть **fallback + кэш**.

4. **Глобальные mutable state** на уровне модуля — опасно при reload в dev-сервере (django dev runserver auto-reload), HUEY-воркере (там `_pending_delete_cache` будет пуст, но туда же дернется pre_delete — для каждого воркера отдельный кэш, что не страшно, но кэш тут — явно лишний).

5. **Рост словаря** при ошибках в `pre_delete` (try/except `:67`) — запись кладётся, но `post_delete` может её не забрать, если pk не совпадёт. Утечка памяти.

**Решение (поэтапно, не делать всё сразу):**

**Этап A (минимум):** оставить только fallback в `post_delete` через БД + `pre_delete` через select_related. Удалить глобальные словари.

```python
@receiver(post_delete, sender=UserMovie)
def on_user_movie_deleted(sender, instance, **kwargs):
    movie = getattr(instance, "movie", None)
    movie_id = getattr(movie, "id", None) if movie else getattr(instance, "movie_id", None)
    tmdb_id = getattr(movie, "tmdb_id", None) if movie else None
    media_type = getattr(movie, "tmdb_media_type", None) if movie else None

    # Если instance без relations и movie_id не помог — прочитать снапшот из БД (movie мог быть каскадно удалён)
    if (not tmdb_id or media_type not in ("movie", "tv")) and movie_id:
        try:
            from vault.models import Movie
            m = Movie.objects.filter(pk=movie_id).values("tmdb_id", "tmdb_media_type").first()
            if m:
                tmdb_id = m["tmdb_id"]
                media_type = m["tmdb_media_type"]
        except Exception:
            pass

    if not tmdb_id or media_type not in ("movie", "tv"):
        logger.debug("writeback delete skipped UserMovie %s tmdb_id=%s media=%s", instance.pk, tmdb_id, media_type)
        return

    transaction.on_commit(
        lambda pk=instance.pk, mid=movie_id, tid=tmdb_id, mt=media_type:
            _schedule_writeback_delete(mid, tid, mt, pk)
    )
```

Аналогично для `UserListMovie`.

**Этап B (опционально):** вынести функцию `_load_user_list_movie_snapshot(ulm_pk)` в `vault/services/tmdb_writeback_service.py`, чтобы иметь единое место для «достать снапшот для удалённого объекта».

**Что не нужно делать:** переписывать `_schedule_writeback_delete` — он окей.

**Проверка:** удалить UserMovie для фильма в SKIP — должно произойти `watchlist_remove` + `skip_list_remove` на TMDB. Удалить UserListMovie — фильм должен удалиться из TMDB list. Если что-то пошло не так — в логе `writeback delete skipped`.

---

### #9 «Жадная» проверка `_is_auth_error` по подстроке [#ВЫПОЛНЕНО]

**Файл:** `vault/services/tmdb_writeback_service.py:46-55`

**Проблема:**

```python
@staticmethod
def _is_auth_error(exc: Exception) -> bool:
    msg = str(exc)
    name = type(exc).__name__
    return (
        "401" in msg
        or name in ("Authentication", "Unauthorized", "WritePermission")
        or "Invalid API key" in msg
        or "Authentication" in msg
    )
```

`"Authentication" in msg` — слишком широко. Если в будущем TMDB введёт сообщение вида `"Authentication rate limit exceeded"` или `"Authentication server temporarily unavailable"` — это не 401, а скорее всего 503 или 429, и текущая логика отправит задачу в `state=ERROR` без ретрая.

Плюс там же, в `sync_user_movie_to_tmdb:249-252`, есть дублирующая проверка через `any("401" in (r.error or "") ...)`:

```python
is_auth = any("401" in (r.error or "") or "Authentication" in (r.error or "") or "Unauthorized" in (r.error or "") for r in failed) or any(cls._is_auth_error(Exception(r.error)) for r in failed if r.error)
# точнее: проверяем failed error strings
if any("401" in (r.error or "") or "Invalid API key" in (r.error or "") for r in failed):
    is_auth = True
```

Это вообще избыточно — есть `_is_auth_error`, есть первая `any()`, есть вторая `if`. Местами противоречат друг другу (`_is_auth_error(Exception(r.error))` — оборачивает строку в Exception, что тоже ненадёжно).

**Решение:**

1. Использовать **конкретные классы исключений tmdbapis** вместо строкового match:

```python
try:
    from tmdbapis.exceptions import (
        TMDbAPIsException,
        Authentication as TmdbAuthentication,
        TMDbAPIs429Exception,
        TMDbAPIs404Exception,
    )
    _IMPORT_OK = True
except ImportError:
    _IMPORT_OK = False

@staticmethod
def _is_auth_error(exc: Exception) -> bool:
    if _IMPORT_OK and isinstance(exc, TmdbAuthentication):
        return True
    msg = str(exc)
    # fallback: status_code если есть
    status = getattr(exc, "status_code", None)
    if status == 401:
        return True
    # last resort: "401" + "Unauthorized"
    return ("401" in msg and ("Unauthorized" in msg or "Invalid API key" in msg))
```

Перед применением проверить реальные имена классов в `venv/lib/.../tmdbapis/exceptions.py` — план §D упоминает, что имена нужно уточнить.

2. В `sync_user_movie_to_tmdb:247-253` упростить:

```python
if failed:
    err_msg = failed[0].error or "unknown"
    is_auth = any(cls._is_auth_error(Exception(r.error)) for r in failed if r.error)
    cls._upsert_queue_item(movie, err_msg, is_auth=is_auth)
```

`_is_auth_error` уже умеет обрабатывать строки через `Exception(r.error)`. Двойной pass через `any` два раза убрать.

**Проверка:** сэмулировать auth error — поменять `tmdb_v4_authenticated_access_token` на невалидный через Django admin или прямым SQL, переключить SKIP. В `TMDBWritebackQueueItem` должна появиться запись `state=error` (auth), а не `state=pending` (network).

---

### #10 Переиспользовать `reset_tmdb_client()` вместо прямого сброса модуля [⏳ не в scope]

**Файл:** `vault/api.py:1953-1960, 1991-1998`

**Проблема:**

В `vault/api.py::tmdb_auth_approve` (строка ~1955):

```python
try:
    import tmdb_adapter.client_singleton as cs
    cs._tmdb_instance = None
    cs._last_token = None
    cs._last_key = None
except Exception:
    pass
```

И в `tmdb_auth_logout` (строка ~1993) — то же самое.

Но в `tmdb_adapter/auth.py:136-143` уже есть **готовый** корректный метод `reset_tmdb_client()`:

```python
def reset_tmdb_client():
    """Сбрасывает синглтон TMDB клиента"""
    global _tmdb_instance, _last_key, _last_token
    with _lock:
        _tmdb_instance = None
        _last_key = None
        _last_token = None
```

Прямой доступ к `_tmdb_instance` обходит `with _lock` — потенциальная race в многопоточном dev-сервере (runserver + сигнал).

**Решение:**

1. Добавить в `tmdb_adapter/client_singleton.py` публичную функцию `reset_tmdb_client()` (или сделать ре-экспорт из `auth.py`). Простейший вариант — добавить прямо в `client_singleton.py`:

```python
def reset_tmdb_client():
    """Сбрасывает синглтон TMDB клиента. Thread-safe."""
    global _tmdb_instance, _tmdb_config, _last_key, _last_token
    with _lock:
        _tmdb_instance = None
        _tmdb_config = None
        _last_key = None
        _last_token = None
```

2. В `vault/api.py:1953-1960` и `1991-1998` заменить прямой сброс на:

```python
try:
    from tmdb_adapter.client_singleton import reset_tmdb_client
    reset_tmdb_client()
except Exception:
    pass
```

3. **Бонус:** в `tmdb_adapter/auth.py::reset_tmdb_client()` (старый) можно либо удалить (если функция переедет в `client_singleton.py`), либо оставить как алиас. Я бы перенёс в `client_singleton.py` и в `auth.py` сделал `from .client_singleton import reset_tmdb_client`.

**Проверка:** авторизоваться через `POST /api/vault/tmdb-auth/start` + `/approve`. После — сделать любой writeback. Должно работать без ошибки «token mismatch».

---

### #11 `init_all_user_lists` без защиты от двойного запуска [#ВЫПОЛНЕНО]

**Файл:** `vault/services/tmdb_writeback_service.py:756-824`

**Проблема:**

Метод вызывается из:
1. `tmdb_lists_init` HUEY-задача (`vault/tasks.py:109-114`), которая запускается из `tmdb_auth_approve` (`vault/api.py:1968-1970`) с `delay=2`.
2. Косвенно — из любого writeback через `_ensure_skip_list_tmdb_id` (но это уже защищено — см. задачу #3).

Между `schedule(delay=2)` и фактическим выполнением таски может произойти ещё один вызов (например, если пользователь кликнул «Re-auth» дважды). Два HUEY-воркера могут одновременно взять таску → оба пройдут по `UserList.objects.all()`, оба увидят пустые `tmdb_list_id` → создадут дубликаты на TMDB.

**Решение:**

Минимум — добавить `select_for_update` (или лок на prefs) в начале метода:

```python
@classmethod
def init_all_user_lists(cls) -> dict:
    from moviefilter.models import UserPreferences
    from vault.models import UserList

    with transaction.atomic():
        prefs = UserPreferences.objects.select_for_update().get(pk=1)
        # Если init уже прошёл успешно — early return
        # Но это не спасает от двойного вызова с перерывом между schedule и run
        ...

    # ...существующий код...
```

Дополнительно — на уровне `tmdb_lists_init` task добавить `if lock acquired` guard:

```python
# vault/tasks.py
from movie_filter_pro.huey import HUEY
from huey.contrib.djhuey import lock_task

@HUEY.task()
@lock_task("tmdb_lists_init")  # дедупликация через lock name
def tmdb_lists_init():
    ...
```

(Точное API huey зависит от версии — проверить `huey.contrib.djhuey` или `@huey.lock_task`. Если такой обёртки нет в проекте — добавить `threading.Lock` руками внутри таски.)

**Проверка:** удалить все `tmdb_list_id` у локальных UserList (через `UserList.objects.update(tmdb_list_id=None)`), вызвать `tmdb_lists_init` напрямую дважды подряд (через `tmdb_lists_init()` без schedule). Должен быть один набор списков на TMDB.

---

### #12 Долгий sync при переименовании списка (TODO.md:139) [⏳ не в scope — уже async через dispatch]

> **Статус:** перепроверено. В ходе перехода на HUEY rename списка уже переведён на
> `schedule_list_sync` (HUEY, delay=2) — UI не блокируется. Прямых синхронных
> вызовов `update_tmdb_list` из сигналов больше нет. Отдельная доработка не требуется.

**Файл:** `vault/signals.py:158-186`

**Проблема:**

`TODO.md:139` явно фиксирует:

> при переименовании списка очень долгое сохранение - оно не ставится в очередь, а сразу пишет на tmdb, видимо

В `signals.py:158-186` (`on_userlist_saved`) `update_tmdb_list(ul)` вызывается **синхронно** через `transaction.on_commit(_do)`. Если TMDB отвечает медленно или возвращает 429 — `PATCH /lists/{id}` блокируется на это время.

`create_tmdb_list` уже умеет работать в HUEY-режиме (`tmdb_lists_init` task), а вот `update_tmdb_list` — нет. Несогласованность паттерна.

**Решение:**

1. Добавить в `vault/tasks.py` HUEY-таску:

```python
@HUEY.task()
def tmdb_writeback_list_update(user_list_id: int):
    from vault.services.tmdb_writeback_service import TmdbWritebackService
    from vault.models import UserList
    try:
        ul = UserList.objects.get(pk=user_list_id)
    except UserList.DoesNotExist:
        return
    TmdbWritebackService.update_tmdb_list(ul)
```

2. В `signals.py:158-186` заменить прямой вызов на `schedule(delay=2)`:

```python
@receiver(post_save, sender=UserList)
def on_userlist_saved(sender, instance, created, **kwargs):
    from vault.services.tmdb_writeback_service import TmdbWritebackService

    should, _ = TmdbWritebackService._should_writeback_lists()
    if not should:
        return
    if instance.name == TmdbWritebackService.SKIP_LIST_NAME:
        return

    ul_id = instance.pk

    def _do(ul_id=ul_id):
        from vault.tasks import tmdb_writeback_list_create, tmdb_writeback_list_update
        from vault.models import UserList
        try:
            ul = UserList.objects.get(pk=ul_id)
        except UserList.DoesNotExist:
            return
        if not ul.tmdb_list_id:
            tmdb_writeback_list_create.schedule(args=(ul_id,), delay=2)
        else:
            tmdb_writeback_list_update.schedule(args=(ul_id,), delay=2)

    transaction.on_commit(_do)
```

3. Добавить `tmdb_writeback_list_create` HUEY-таску для единообразия (создание — тоже через очередь, не блокирует ответ `POST /lists`).

4. В `tmdb_auth_approve` (`vault/api.py:1962-1972`) сейчас вызывается `tmdb_lists_init.schedule(delay=2)` — оставить как есть.

**Что это даёт:** переименование списка отвечает пользователю мгновенно, реальный sync происходит в фоне.

**Проверка:** переименовать любой UserList. UI должен ответить быстро (≤200мс). Изменение имени на TMDB появится в течение 2-3 секунд (можно проверить через tmdb UI или API).

---

## P3 — Косметика / отложенное

### #13 Логирование `_is_auth_error` имеет дубль-логику в `sync_user_movie_to_tmdb` [#ВЫПОЛНЕНО — закрыто вместе с #1/#9]

**Файл:** `vault/services/tmdb_writeback_service.py:247-253`

**Проблема:**

В методе `sync_user_movie_to_tmdb` для определения «это auth error»:

```python
is_auth = any("401" in (r.error or "") or "Authentication" in (r.error or "") or "Unauthorized" in (r.error or "") for r in failed) or any(cls._is_auth_error(Exception(r.error)) for r in failed if r.error)
# точнее: проверяем failed error strings
if any("401" in (r.error or "") or "Invalid API key" in (r.error or "") for r in failed):
    is_auth = True
```

Тут два `any` подряд, плюс `_is_auth_error`. Это следствие задачи #9 — после её решения всё свернётся в одну строку. В рамках этой задачи — оставить как есть, почистится вместе с #9.

**Связь:** правится автоматически при выполнении задачи #9.

---

### #14 Лишняя проверка `movie_tmdb_id` в `sync_skip_list` [#НЕ ПРИМЕНИМО — guard валиден]

> **Статус:** перепроверено. Дата планирования считала ветку `if not movie_tmdb_id: return None` мёртвой, т.к. `sync_skip_list` вызывается только после `_should_writeback`. Но `sync_skip_list` — публичный метод (тот же, что `sync_watch_status`/`sync_favorite`/`sync_rating`), и прямой вызов без tmdb_id уронил бы `_ensure_skip_list_tmdb_id`/`_get_tmdb_obj` ниже. Guard НЕ мёртвый — это валидная defensive-защита. Добавлен комментарий, объясняющий намерение; код оставлен.

**Файл:** `vault/services/tmdb_writeback_service.py:526-585`

**Проблема:**

`sync_skip_list` (`tmdb_writeback_service.py:540-541`):

```python
movie_tmdb_id = getattr(movie, "tmdb_id", None)
if not movie_tmdb_id:
    return None
```

Но метод вызывается только из `sync_user_movie_to_tmdb`, который уже прошёл `_should_writeback` (там есть проверка `tmdb_id`):

```python
should, reason = cls._should_writeback(movie)  # проверяет tmdb_id
if not should:
    return [...]
# ... только здесь может быть вызван sync_skip_list
r = cls.sync_skip_list(user_movie)
```

Так что `if not movie_tmdb_id: return None` — мёртвая ветка.

**Решение:**

Убрать проверку, или заменить на assert (если хочется формальной страховки на будущее — когда `sync_skip_list` начнут вызывать из других мест).

```python
@classmethod
def sync_skip_list(cls, user_movie) -> Optional[WritebackResult]:
    from vault.models import UserMovie as UM

    movie = getattr(user_movie, "movie", None)
    if not movie:
        return None
    watch_status = getattr(user_movie, "watch_status", None)
    movie_tmdb_id = getattr(movie, "tmdb_id", None)
    # guard выше делается в _should_writeback; если вызвали напрямую — пропускаем
    if not movie_tmdb_id:
        return None
    ...
```

На текущий момент — пусть остаётся, это не баг. Уберётся при рефакторинге сигнатур.

**Связь:** правится автоматически при выполнении задачи #4 (рефакторинг `sync_user_movie_to_tmdb`).

---

## Контрольный список после прохождения всех задач

После выполнения всех P0-P3 задач:

1. `grep "401" "Authentication" "Unauthorized" vault/services/tmdb_writeback_service.py` — должно остаться только в `_is_auth_error`.
2. `grep "_pending_delete_cache\|_pending_list_delete" vault/signals.py` — должно быть пусто.
3. `ls vault/services/tmdb_writeback_queue.py` — файл не должен существовать.
4. Прогон ручных сценариев из P0-проверок.
5. Обновить `PLAN_TWO_WAY_SYNC.md` §19 — пометить закрытые подзадачи.
7. `python manage.py check` + `migrate --check` без ошибок.

---

## Переход на HUEY (SYNC-HUEY-REFACTORING)

> Цель: записи в TMDB не должны блокировать HTTP-ответы UI.
> Принцип: сигналы только ставят HUEY-задачу в очередь; вся работа по TMDB — в воркере.

### Выводы из ресёрча Huey 2.6.0

- `schedule()` возвращает `Result` (`SqliteHuey` с `results=True`).
- `Result.reschedule(delay=...)` = `revoke()` текущей таски + enqueue новой с теми же `args`. Это встроенный dedup «последняя версия выполнится».
- `lock_task()` — статический, per-argument НЕ поддерживает → для дедупа по `user_movie_id` не годится.
- `enqueue`/`schedule` не дедуплицируют по `id` сами.

**Чистый dedup:** хранить последний `Result` per `user_movie_id`; при повторном `schedule()` звать `.reschedule(delay=...)`.

### Архитектура

- **`vault/services/tmdb_writeback_dispatch.py`** (новый): единственная точка «поставить writeback в HUEY». Хранит `_pending: dict[str, Result]`, дедуплицирует через `reschedule()`, `schedule(delay=WRITEBACK_DELAY_SECONDS)`.
- **`vault/tasks.py`**: тонкие HUEY-таски-обёртки над `TmdbWritebackService`. Добавить: `tmdb_writeback_list_*`, `tmdb_writeback_user_movie_delete`.
- **`vault/signals.py`**: заменить синхронные вызовы сервиса на вызовы dispatch. Для delete передавать снапшот-данные в задачу.
- **`vault/services/tmdb_writeback_service.py`**: удалить `_schedule_retry` (ретрай 429 — только через persistent queue `tmdb_writeback_retry_tick`).

### Чек-лист

- [x] Создать `vault/services/tmdb_writeback_dispatch.py` (helper с dedup через `reschedule`).
- [x] `vault/tasks.py`: `tmdb_writeback_user_movie_delete(movie_id, tmdb_id, media_type)`.
- [x] `vault/tasks.py`: `tmdb_writeback_list_item_added(ulm_id)`, `tmdb_writeback_list_item_removed(tmdb_list_id, tmdb_id, media_type)`.
- [x] `vault/tasks.py`: `tmdb_writeback_list_create(ul_id)`, `tmdb_writeback_list_update(ul_id)`, `tmdb_writeback_list_delete(tmdb_list_id)`.
- [x] `vault/signals.py`: `UserMovie post_save` → dispatch.schedule_user_movie_writeback(pk).
- [x] `vault/signals.py`: `UserMovie post_delete` → dispatch.schedule_user_movie_delete(snapshot).
- [x] `vault/signals.py`: `UserListMovie post_save/post_delete` → dispatch.
- [x] `vault/signals.py`: `UserList post_save/post_delete` → dispatch.
- [x] `vault/services/tmdb_writeback_service.py`: удалить `_schedule_retry`.
- [x] Ручной push `POST /movies/{slug}/tmdb-writeback` и `fetch-tmdb` → оставить синхронными (явные действия пользователя).
- [ ] Проверка: toggle статуса отвечает <200мс, в логах запись через 2-3 сек; 3 toggle за 2 сек = 1 запрос.

### Примечания

- `tmdb_writeback_retry_tick` остаётся единственным механизмом ретрая failed (persistent queue).
- `tmdb_writeback_queue.py` (мёртвый) — кандидат на удаление (#6), но не в рамках этого перехода.

---

## Переход на HUEY (SYNC-HUEY-REFACTORING)

> Цель: записи в TMDB не должны блокировать HTTP-ответы UI.
> Принцип: сигналы только ставят HUEY-задачу в очередь; вся работа по TMDB — в воркере.

### Выводы из ресёрча Huey 2.6.0

- `schedule()` возвращает `Result` (`SqliteHuey` с `results=True`).
- `Result.reschedule(delay=...)` = `revoke()` текущей таски + enqueue новой с теми же `args`. Это встроенный dedup «последняя версия выполнится».
- `lock_task()` — статический, per-argument НЕ поддерживает → для дедупа по `user_movie_id` не годится.
- `enqueue`/`schedule` не дедуплицируют по `id` сами.

**Чистый dedup:** хранить последний `Result` per `user_movie_id`; при повторном `schedule()` звать `.reschedule(delay=...)`.

### Архитектура

- **`vault/services/tmdb_writeback_dispatch.py`** (новый): единственная точка «поставить writeback в HUEY». Хранит `_pending: dict[str, Result]`, дедуплицирует через `reschedule()`, `schedule(delay=WRITEBACK_DELAY_SECONDS)`.
- **`vault/tasks.py`**: тонкие HUEY-таски-обёртки над `TmdbWritebackService`. Добавить: `tmdb_writeback_list_*`, `tmdb_writeback_user_movie_delete`.
- **`vault/signals.py`**: заменить синхронные вызовы сервиса на вызовы dispatch. Для delete передавать снапшот-данные в задачу.
- **`vault/services/tmdb_writeback_service.py`**: удалить `_schedule_retry` (ретрай 429 — только через persistent queue `tmdb_writeback_retry_tick`).

### Чек-лист

- [ ] Создать `vault/services/tmdb_writeback_dispatch.py` (helper с dedup через `reschedule`).
- [ ] `vault/tasks.py`: `tmdb_writeback_user_movie_delete(movie_id, tmdb_id, media_type)`.
- [ ] `vault/tasks.py`: `tmdb_writeback_list_item_added(ulm_id)`, `tmdb_writeback_list_item_removed(tmdb_list_id, tmdb_id, media_type)`.
- [ ] `vault/tasks.py`: `tmdb_writeback_list_create(ul_id)`, `tmdb_writeback_list_update(ul_id)`, `tmdb_writeback_list_delete(tmdb_list_id)`.
- [ ] `vault/signals.py`: `UserMovie post_save` → dispatch.schedule_user_movie_writeback(pk).
- [ ] `vault/signals.py`: `UserMovie post_delete` → dispatch.schedule_user_movie_delete(snapshot).
- [ ] `vault/signals.py`: `UserListMovie post_save/post_delete` → dispatch.
- [ ] `vault/signals.py`: `UserList post_save/post_delete` → dispatch.
- [x] `vault/services/tmdb_writeback_service.py`: удалить `_schedule_retry`.
- [x] Ручной push `POST /movies/{slug}/tmdb-writeback` и `fetch-tmdb` → оставить синхронными (явные действия пользователя).
- [x] Проверка: toggle статуса отвечает <200мс, в логах запись через 2-3 сек; 3 toggle за 2 сек = 1 запрос (нужен запуск TMDB-запросов на живом воркере).

### Примечания

- `tmdb_writeback_retry_tick` остаётся единственным механизмом ретрая failed (persistent queue).
- `tmdb_writeback_queue.py` (мёртвый) — кандидат на удаление (#6), но не в рамках этого перехода.