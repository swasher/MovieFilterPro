# План оптимизации синхронизации TMDB (10K+ фильмов)

> Цель: минимизировать лишние API-вызовы при массовой синхронизации Vault ↔ TMDB.
> Контекст: ~10000 фильмов, надёжность важнее скорости.

---

## R1. Δ-синхронизация writeback'а — вызывать только реально изменённые sub-sync'и

**Проблема**: `sync_user_movie_to_tmdb()` вызывается при каждом `post_save UserMovie` и 执行няет ВСЕ sub-sync'и (watchlist, favorite, rating, skip_list, custom lists) вне зависимости от того, что реально поменял пользователь. Ситуация «положить в список» порождает 4-5+ API-вызовов, хотя нужен один.

**Текущий flow**:
```
UserMovie.save() → post_save → sync_user_movie_to_tmdb()
  → sync_watch_status()       ← вызывается всегда
  → sync_favorite()           ← вызывается всегда
  → sync_rating()             ← вызывается всегда
  → sync_skip_list()          ← вызывается всегда
  → sync_list_item_added() ×N ← вызывается всегда
```

**Предлагаемое**:
1. В сигнале (`vault/signals.py`) при `post_save` сравнивать `instance` с предыдущим состоянием через `UserMovie.objects.get(pk=instance.pk)` или через `pre_save` сигнал.
2. Собирать список `changed_fields: list[str]` (например, `["watch_status"]`).
3. Передавать `changed_fields` через dispatch в сервис.
4. В `sync_user_movie_to_tmdb()` вызывать только sub-sync'и для изменённых полей.

```python
# signals.py — упрощённо
@receiver(post_save, sender=UserMovie)
def on_user_movie_saved(sender, instance, created, **kwargs):
    if created:
        changed = ["watch_status", "is_favorite", "rating"]
    else:
        old = UserMovie.objects.get(pk=instance.pk)
        changed = []
        if old.watch_status != instance.watch_status:
            changed.append("watch_status")
        if old.is_favorite != instance.is_favorite:
            changed.append("is_favorite")
        if old.rating != instance.rating:
            changed.append("rating")
    TmdbWritebackDispatch.schedule_user_movie_writeback(pk, changed_fields=changed)
```

```python
# tmdb_writeback_service.py
def sync_user_movie_to_tmdb(user_movie, changed_fields=None):
    if changed_fields is None:
        changed_fields = ["watch_status", "is_favorite", "rating", "skip_list", "lists"]
    
    if "watch_status" in changed_fields:
        r = sync_watch_status(user_movie)
        if r: results.append(r)
    if "is_favorite" in changed_fields:
        r = sync_favorite(user_movie)
        if r: results.append(r)
    if "rating" in changed_fields:
        r = sync_rating(user_movie)
        if r: results.append(r)
    if "skip_list" in changed_fields:
        r = sync_skip_list(user_movie)
        if r: results.append(r)
    if "lists" in changed_fields:
        for lm in UserListMovie.objects.filter(movie=movie).select_related("user_list"):
            r = sync_list_item_added(lm)
            if r: results.append(r)
```

**Экономия**: «добавить в watchlist» → 1 вызов вместо 4-5+.

**Нюансы**:
- При `created=True` все поля новые → запускаем всё (как сейчас).
- При удалении `UserMovie` — `sync_user_movie_deleted` и так делает cleanup (watchlist_remove, favorite_remove, delete_rating) — это корректно, оставляем как есть.
- Сигнал `pre_delete` уже сохраняет снапшот — там менять ничего не надо.

**Файлы**: `vault/signals.py`, `vault/services/tmdb_writeback_dispatch.py`, `vault/services/tmdb_writeback_service.py`.

---

## R2. Батчинг list_add_items / list_remove_items по `tmdb_list_id`

**Проблема**: Каждое `sync_list_item_added()` делает отдельный `list_add_items()` API-вызов. Если фильм в 5 пользовательских списках — 5 вызовов. Если синхронизируется 1000 фильмов в один список — 1000 вызовов. TMDB API v4 поддерживает передачу массива items в одном вызове (`list_add_items(list_id, items=[...])`), но мы не используем эту возможность.

**Текущий flow**:
```
Movie A → List1 → list_add_items(List1, [A])    ← API #1
Movie A → List2 → list_add_items(List2, [A])    ← API #2
Movie B → List1 → list_add_items(List1, [B])    ← API #3
Movie B → List2 → list_add_items(List2, [B])    ← API #4
```

**Предлагаемое**: двухфазный подход — **сбор + исполнение**.

**Фаза 1 — Аккумуляция**: сигналы пишут операции в аккумулятор вместо немедленного выполнения.

**Фаза 2 — Flush**: по завершении batch (или по таймеру) выполняются сгруппированные вызовы:

```
list_add_items(List1, [A, B])    ← 1 API-вызов
list_add_items(List2, [A, B])    ← 1 API-вызов
```

```python
class TmdbWritebackListBatcher:
    """Аккумулятор операций с списками для последующего батчевого исполнения."""
    
    _additions: dict[int, list[dict]] = defaultdict(list)
    _removals: dict[int, list[dict]] = defaultdict(list)
    
    @classmethod
    def queue_add(cls, tmdb_list_id: int, media_type: str, media_id: int):
        cls._additions[tmdb_list_id].append({
            "media_type": media_type,
            "media_id": media_id,
        })
    
    @classmethod
    def queue_remove(cls, tmdb_list_id: int, media_type: str, media_id: int):
        cls._removals[tmdb_list_id].append({
            "media_type": media_type,
            "media_id": media_id,
        })
    
    @classmethod
    def flush(cls) -> list[WritebackResult]:
        results = []
        for list_id, items in cls._additions.items():
            tmdb.list_add_items(list_id=list_id, items=items)
            results.append(WritebackResult(success=True, action="list_add", ...))
        for list_id, items in cls._removals.items():
            tmdb.list_remove_items(list_id=list_id, items=items)
            results.append(WritebackResult(success=True, action="list_remove", ...))
        cls._additions.clear()
        cls._removals.clear()
        return results
```

**Интеграция**:
- `sync_list_item_added()` перестаёт делать API-вызов и вместо этого делает `Batcher.queue_add(list_id, media_type, media_id)`.
- `sync_list_item_removed()` → `Batcher.queue_remove(...)`.
- Flush вызывается по завершении batch-обработки или через периодический HUEY-тик.

**Экономия**: 1000 фильмов × 5 списков = 5000 вызовов → 500 вызовов (1 на каждый список × число уникальных списков).

**Нюансы**:
- Нужен механизм flush'а: при завершении batch, по таймеру (например, каждые 30 сек), или при достижении порога (например, 500 накопленных операций).
- Обработка ошибок: если batch частично провалился — нужно логировать какие items не удалось добавить (TMDB возвращает массив с `success` для каждого item).
- Удаление `UserListMovie` (post_delete) — тут аккумулятор может не помочь, т.к. это поштучные события. Но можно и сюда добавить аккумуляцию.

**Файлы**: новый файл `vault/services/tmdb_writeback_batcher.py` (или встроить в `tmdb_writeback_service.py`), `vault/services/tmdb_writeback_dispatch.py`, `vault/tasks.py`.

---

## R3. Pre-fetch всех `tmdb_list_id` маппинга

**Проблема**: В `sync_list_item_added()` каждый раз проверяется `user_list.tmdb_list_id` через БД. Если `tmdb_list_id` пуст — вызывается `create_tmdb_list()`, который делает API-вызов `list_get_list` для поиска списка, а затем `list_create_list`. Для каждого списка без ID — минимум 1-2 лишних API-вызова при каждом добавлении фильма.

**Текущий flow**:
```
sync_list_item_added(list_movie):
  → SELECT UserList WHERE id = ...    ← DB
  → if not tmdb_list_id:
      → list_get_list()              ← API #1 (проверка)
      → list_create_list()           ← API #2 (создание)
```

**Предлагаемое**:
1. Перед началом batch-синхронизации загрузить маппинг `{user_list_id: tmdb_list_id}` один раз:
   ```python
   LIST_ID_CACHE = {ul.id: ul.tmdb_list_id for ul in UserList.objects.all()}
   ```
2. В `sync_list_item_added()` читать из кэша вместо БД.
3. Создать списки на TMDB заранее (в `init_all_user_lists()` или аналогичном предварительном шаге), чтобы кэш был полным.

```python
# Вспомогательный модуль / сервис
class ListIdCache:
    """Кэш UserList → tmdb_list_id. Загружается один раз."""
    _cache: dict[int, int | None] = {}
    _loaded = False
    
    @classmethod
    def load(cls):
        if cls._loaded:
            return
        cls._cache = {
            ul.id: ul.tmdb_list_id 
            for ul in UserList.objects.all()
        }
        cls._loaded = True
    
    @classmethod
    def get(cls, user_list_id: int) -> int | None:
        return cls._cache.get(user_list_id)
    
    @classmethod
    def set(cls, user_list_id: int, tmdb_list_id: int | None):
        cls._cache[user_list_id] = tmdb_list_id
```

**Экономия**: устраняет N × 1-2 лишних API-вызова для N списков без ID. Также убирает N лишних SELECT в БД.

**Нюансы**:
- Кэш нужно инвалидировать при создании нового списка (но новые списки создаются через `create_tmdb_list`, который обновляет и кэш).
- Для редких случаев, когда список удалён на TMDB вручную — сброс `tmdb_list_id` в None и пересоздание при следующей попытке (паттерн уже работает для skip-листа).

**Файлы**: `vault/services/tmdb_writeback_service.py`, `vault/services/tmdb_sync_queue_service.py` (или общий сервис кэша).

---

## R4. Убрать `list_get_list` из `init_all_user_lists()` — доверять кэшу

**Проблема**: `init_all_user_lists()` в `tmdb_writeback_service.py` (строки 826-844) для каждого списка с `tmdb_list_id` вызывает `list_get_list(list_id)` чтобы проверить, существует ли он на TMDB. Для 100 списков = 100 API-вызовов. На практике списки редко удаляются вручную.

**Текущий flow**:
```python
for ul in all_lists:
    if ul.tmdb_list_id:
        api4.list_get_list(list_id=int(ul.tmdb_list_id))  # ← лишний вызов
    # ... если упал 404 → пересоздать
```

**Предлагаемое**:
1. Убрать `list_get_list` из цикла. Просто пропускать списки с заполненным `tmdb_list_id`.
2. Если при реальной операции `list_add_items` / `list_remove_items` вернёт 404 — сбросить `tmdb_list_id` в None и пересоздать список. Паттерн уже реализован для skip-листа — распространить на пользовательские списки.

```python
# Было:
for ul in all_lists:
    if ul.tmdb_list_id:
        try:
            api4.list_get_list(list_id=int(ul.tmdb_list_id))  # УБРАТЬ
        except Exception:
            # пересоздать
            ...

# Стало:
for ul in all_lists:
    if not ul.tmdb_list_id:
        to_create.append(ul)
# Списки с tmdb_list_id — считаем живыми.
# Если при add/remove вернётся 404 → сброс кэша + пересоздание.
```

**Экономия**: N API-вызовов → 0 для N списков с известным ID.

**Нюансы**:
- Если пользователь удалил список на TMDB вручную — мы не узнаем об этом до следующей операции с этим списком. Это допустимо (согласно паттерну skip-листа).
- При `list_add_items` получаем 404 → `_ensure_skip_list_tmdb_id`-стиль: сбрасываем `tmdb_list_id`, создаём заново, повторяем операцию.

**Файлы**: `vault/services/tmdb_writeback_service.py` (`init_all_user_lists` и `sync_list_item_added`/`sync_list_item_removed` для обработки 404).

---

## R5. Оптимизация read-sync'а для массовой синхронизации

**Проблема**: При первичной синхронизации 10K фильмов каждый вызов `tmdb.movie()` / `tmdb.tv_show()` возвращает полный payload с cast, crew, и т.д. Это огромные данные. Cast/crew нужны не всегда — например, при первом импорте можно их отложить.

**Текущий flow**:
```
sync_movie(movie):
  → tmdb.movie(tmdb_id)  ← возвращает: title, overview, cast, crew, genres, videos, images, keywords, ...
  → _sync_movie_persons() → для каждого person_id в cast/crew → tmdb.person(person_id)
  → _sync_seasons_and_episodes() → tmdb.tv_season(tmdb_id, season) для каждого сезона
```

**Предлагаемое**: добавить параметр `sync_mode` с вариантами:

```python
SyncMode = Literal["full", "basic"]

def sync_movie(movie, force_rematch=False, selected_candidate=None, sync_mode="full"):
    ...
    details, media_type = cls._load_details(tmdb, candidate, sync_mode=sync_mode)
```

- **`sync_mode="basic"`** (по умолчанию для bulk): загружать только минимальные данные:
  - Title, original_title, overview, release_date, poster_path, backdrop_path
  - Genres, countries, vote_average, vote_count
  - IMDB ID (для OMDB)
  - **Пропустить**: cast, crew, videos, keywords, reviews, release_dates
- **`sync_mode="full"`** (по умолчанию для ручного sync): всё как сейчас

**Реализация**: TMDB API поддерживает `append_to_response` для расширения данных, но для минимизации — просто не запрашивать лишние секции. Впрочем, `tmdbapis` библиотека возвращает весь payload по умолчанию. Альтернатива: использовать `_load_details` с меньшим объёмом данных, но это зависит от библиотеки.

**Простой подход**: не изменять API-вызов, а вместо этого:
- В `_sync_movie_persons()` при `sync_mode="basic"` пропустить полностью (return True без изменений)
- В `_sync_seasons_and_episodes()` при `sync_mode="basic"` пропустить
- В `_apply_keywords()` пропустить
- В `_sync_collection()` пропустить

```python
if sync_mode == "basic":
    # Только основные поля, без персон и сезонов
    cls._apply_movie_payload(movie, details, set_field)
    cls._sync_genres(movie, getattr(details, "genres", None))
    cls._sync_countries(...)
    # skip persons, seasons, keywords, collection
else:
    # Полный sync — как сейчас
    cls._sync_movie_persons(...)
    ...
```

**Экономия**: для 10K фильмов — исключение ~10K calls к `_sync_movie_persons` (каждый с персональными деталями) + исключение N calls к `tmdb.tv_season()` для каждого сезона каждого сериала.

**Нюансы**:
- Персон и сезонов можно подтянуть later-on-demand при открытии фильма.
- OMDB sync оставить — imdb_id нужен для рейтингов.
- Флаг `sync_mode` передавать через `TMDBSyncQueueItem.sync_mode` или из настроек UserPreferences.

**Файлы**: `vault/services/tmdb_movie_sync_service.py`, `vault/models.py` (добавить поле sync_mode в TMDBSyncQueueItem или UserPreferences), `vault/services/tmdb_sync_queue_service.py`.

---

## R6. Пороги и ретраи: управляемая скорость + устойчивость к ошибкам

**Проблема**: 10K фильмов × 5 writeback-операций = до 50K API-вызовов. TMDB имеет rate limit (~40 запросов / 10 секунд для v4). Без управления скоростью получим массовые 429-ошибки, попадание в persistent queue и бесконечные ретраи.

**Текущий state**:
- `WRITEBACK_DELAY_SECONDS = 2` — задержка между задачами в HUEY (дедупликация, не rate-limit).
- `tmdb_writeback_retry_tick` — раз в 10 минут, лимит 20 ретраев за тик.
- Нет явного контроля скорости записи.

**Предлагаемое**:

### 6a. Контроль скорости записи (write rate limiter)

```python
class WriteRateLimiter:
    """Ограничитель скорости записи в TMDB."""
    
    # TMDB v4: ~40 requests / 10 seconds = ~4/sec
    # Берём запас: 2 req/sec для надёжности
    MAX_PER_SECOND = 2
    MIN_INTERVAL = 0.5  # секунд между вызовами
    
    def __init__(self):
        self._last_call = 0.0
    
    def wait(self):
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self.MIN_INTERVAL:
            time.sleep(self.MIN_INTERVAL - elapsed)
        self._last_call = time.monotonic()
```

- Интегрировать в `TmdbWritebackService._get_tmdb_obj()` или в `sync_*` методы.
- Или использовать HUEY rate-limit (`@HUEY.task(rate_limit="2/s")`), если Huey поддерживает.

### 6b. Экспоненциальный backoff для 429

**Текущий state**: при 429 задача уходит в persistent queue с `next_retry_at = now + 10 min`. Фиксированная задержка.

**Предлагаемое**:
- Первый 429 → retry через 10 сек
- Второй 429 → retry через 30 сек
- Третий 429 → retry через 60 сек
- Максимум ~5 минут

```python
def _get_retry_delay(attempts: int) -> int:
    """Экспоненциальный backoff для rate limit."""
    delays = [10, 30, 60, 120, 300]
    return delays[min(attempts - 1, len(delays) - 1)]
```

### 6c. Пакетная обработка с паузами

При bulk sync 1000+ фильмов:
- Разбить на батчи по 50-100 фильмов
- Пауза 1-2 сек между батчами
- После каждого батча — проверка очереди ошибок

```python
BATCH_SIZE = 50
BATCH_PAUSE_SECONDS = 2

for batch_start in range(0, total_movies, BATCH_SIZE):
    batch = movies[batch_start:batch_start + BATCH_SIZE]
    for movie in batch:
        process_movie(movie)
    time.sleep(BATCH_PAUSE_SECONDS)
```

### 6d. Graceful degradation

- Если persistent queue растёт > 1000 items — останавливать синхронизацию и уведомлять пользователя.
- Если 401 (auth error) — останавливать всё и требовать re-auth. Не клать в ретрай-цикл.
- Логи: счётчик успехов/провалов/ретраев каждые 100 фильмов.

**Экономия/выгода**: предотвращает каскадные ошибки, ускоряет ретраи, снижает нагрузку на TMDB API.

**Файлы**: `vault/services/tmdb_writeback_service.py` (rate limiter, backoff), `vault/tasks.py` (batch task), `vault/models.py` (опционально: TMDBSyncQueueItem для batch mode).

---

## Сводная таблица экономии

| Сценарий | Сейчас | После оптимизации |
|----------|--------|--------------------|
| «Добавить в watchlist» | 4-5 API вызовов | **1 вызов** (R1) |
| «Включить heart» | 4-5 API вызовов | **1 вызов** (R1) |
| 1000 фильмов → 1 список | 1000+ вызовов | **1 вызов** (R2) |
| 1000 фильмов × 5 списков | 5000+ вызовов | **500 вызовов** (R2) |
| `init_all_user_lists` 100 списков | 100 вызовов | **0** (R4) |
| Базовый read-sync 10K фильмов | cast + crew + seasons | **только основные** (R5) |
| Rate limit violations | 429 → 10 мин ретрай | **backoff 10-300 сек** (R6) |

---

## Порядок реализации

1. **R1** (Δ-writeback) — самый простой и даёт максимальный эффект. Начать здесь.
2. **R3** (pre-fetch list IDs) — просто, устраняет лишние DB/API запросы.
3. **R4** (убрать list_get_list) — одна правка, сразу N вызовов экономии.
4. **R2** (batch lists) — сложнее, но самый большой выигрыш при массовом sync'е.
5. **R5** (read-sync basic mode) — для первичной загрузки 10K фильмов.
6. **R6** (rate limiter + backoff) — инфраструктура, нужно до запуска массовой синхронизации.