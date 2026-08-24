# План: Двусторонняя синхронизация Vault <-> TMDB

## 1. Контекст и текущее состояние

### Что есть сейчас (только READ из TMDB)
- Поиск и импорт фильмов/сериалов из TMDB в Vault (`TMDBMovieImportService`)
- Массовая синхронизация метаданных через очередь (`TMDBSyncQueueService`)
- OAuth V4 авторизация для получения write access token (`tmdb_adapter/auth.py`)

### Чего нет (WRITE в TMDB)
- Нет ни одной операции обратной записи данных из Vault в TMDB
- UserMovie (watch_status, rating, is_favorite) хранится **только локально**
- UserList (пользовательские списки) **только локальные**
- Сезоны/эпизоды — **только локальные**

### Что нужно реализовать
Двусторонняя синхронизация: при изменении данных в Vault автоматически обновлять их на TMDB.

---

## 2. Маппинг данных: Vault <-> TMDB

### 2.1 Статус просмотра (watch_status)

| Vault (`UserMovie.watch_status`) | TMDB watchlist | TMDB favorite |
|-----------------------------------|----------------|---------------|
| `WATCHED (1)` — Просмотрено | ❌ Убрать из watchlist | — |
| `PLAN (2)` — Буду смотреть | ✅ Добавить в watchlist | — |
| `SKIP (3)` — Не буду смотреть | ❌ Убрать из watchlist | — |
| `None` | ❌ Убрать из watchlist | — |

**Логика映射:**
- `PLAN` → `movie.add_to_watchlist()` / `tv.add_to_watchlist()`
- `WATCHED` / `SKIP` / `None` → `movie.remove_from_watchlist()` / `tv.remove_from_watchlist()`

### 2.2 Избранное (is_favorite)

| Vault (`UserMovie.is_favorite`) | TMDB favorite |
|---------------------------------|---------------|
| `True` | ✅ `movie.mark_as_favorite()` / `tv.mark_as_favorite()` |
| `False` | ❌ `movie.remove_as_favorite()` / `tv.remove_as_favorite()` |

### 2.3 Оценка (rating)

| Vault (`UserMovie.rating`) | TMDB rating |
|----------------------------|-------------|
| `1-10` | `movie.rate(rating)` / `tv.rate(rating)` |
| `None` | `movie.delete_rating()` / `tv.delete_rating()` |

**Важно:** TMDB использует шкалу 0.5–10.0 с шагом 0.5. Vault использует 1–10 (целые). Конвертация: `vault_rating` передаётся как есть (TMDB примет целые числа).

### 2.4 Пользовательские списки (UserList -> TMDB Lists)

| Vault (`UserList`) | TMDB List |
|--------------------|-----------|
| Создание нового UserList | `tmdb.create_list(name, ...)` → сохранить `tmdb_list_id` |
| Добавление фильма в UserList | `api4.list_add_items(tmdb_list_id, [{media_type, media_id}])` |
| Удаление фильма из UserList | `api4.list_remove_items(tmdb_list_id, [{media_type, media_id}])` |
| Удаление UserList | `api4.list_delete_list(tmdb_list_id)` |

### 2.5 Сезоны/эпизоды (UserSeason)

| Vault (`UserSeason`) | TMDB |
|----------------------|------|
| `watch_status=WATCHED` | Нет прямого API (только rating) |
| `rating` | `episode.rate(rating)` |

**Решение:** Сезоны/эпизоды пока НЕ синхронизировать через write-back. TMDB не поддерживает watchlist/favorite для сезонов/эпизодов. Только рейтинги — как отдельная фаза.

---

## 3. Архитектура сервисного слоя

### 3.1 Структура файлов

```
vault/services/
├── tmdb_writeback_service.py      # ОСНОВНОЙ: координация write-back операций
├── tmdb_writeback_queue.py        # Очередь фоновых write-back задач
├── tmdb_movie_sync_service.py     # (существующий) read-only sync
├── tmdb_movie_import_service.py   # (существующий) import
├── tmdb_movie_matching_service.py # (существующий) matching
├── tmdb_sync_queue_service.py     # (существующий) read-only queue
├── movie_status_service.py        # (существующий) mutation point
├── season_status_service.py       # (существующий) mutation point
└── ...
```

### 3.2 Единая точка входа: `TmdbWritebackService`

```python
vault/services/tmdb_writeback_service.py
```

**Ключевой принцип:** Сервис НЕ вызывается напрямую из API-эндпоинтов. Вместо этого он подключается как **post-save hook** к `MovieStatusService` и `UserList` операциям.

#### Основной интерфейс:

```python
class TmdbWritebackService:
    """Сервис обратной записи данных Vault в TMDB."""

    # --- Основные методы ---

    @classmethod
    def sync_user_movie_to_tmdb(cls, user_movie: UserMovie) -> WritebackResult:
        """
        Синхронизировать ОДИН UserMovie с TMDB.
        Вызывается при изменении watch_status, is_favorite, rating.
        """
        ...

    @classmethod
    def sync_watch_status(cls, user, movie, old_status, new_status) -> WritebackResult:
        """Синхронизировать статус просмотра."""
        ...

    @classmethod
    def sync_favorite(cls, user, movie, is_favorite: bool) -> WritebackResult:
        """Синхронизировать избранное."""
        ...

    @classmethod
    def sync_rating(cls, user, movie, rating: Optional[int]) -> WritebackResult:
        """Синхронизировать оценку."""
        ...

    @classmethod
    def sync_user_list_add(cls, user_list: UserList, movie: Movie) -> WritebackResult:
        """Добавить фильм в TMDB list."""
        ...

    @classmethod
    def sync_user_list_remove(cls, user_list: UserList, movie: Movie) -> WritebackResult:
        """Удалить фильм из TMDB list."""
        ...

    @classmethod
    def create_tmdb_list(cls, user_list: UserList) -> WritebackResult:
        """Создать список на TMDB."""
        ...

    @classmethod
    def delete_tmdb_list(cls, user_list: UserList) -> WritebackResult:
        """Удалить список на TMDB."""
        ...

    # --- Bulk-операции ---

    @classmethod
    def sync_all_user_movies(cls, user) -> BulkWritebackResult:
        """
        Полная синхронизация всех UserMovie пользователя с TMDB.
        Используется при first-time setup или принудительной синхронизации.
        """
        ...
```

### 3.3 Вспомогательные классы

```python
@dataclass
class WritebackResult:
    success: bool
    action: str           # "watchlist_add", "watchlist_remove", "favorite_add", "favorite_remove", "rate", "unrate", "list_add", "list_remove"
    tmdb_id: int
    media_type: str       # "movie" или "tv"
    error: Optional[str] = None
    retry_after: Optional[int] = None  # секунды до retry (для 429)

@dataclass
class BulkWritebackResult:
    total: int
    synced: int
    failed: int
    skipped: int          # нет tmdb_id
    errors: List[WritebackResult]
```

---

## 4. Подключение к точкам мутации

### 4.1 Вариант A: Django Signals (post_save) — РЕКОМЕНДУЕМЫЙ

Подключаемся к `post_save` сигналу модели `UserMovie`.

```python
# vault/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from vault.models import UserMovie, UserList, UserListMovie

@receiver(post_save, sender=UserMovie)
def on_user_movie_saved(sender, instance, created, **kwargs):
    """При сохранении UserMovie — запускаем write-back."""
    from vault.services.tmdb_writeback_service import TmdbWritebackService
    TmdbWritebackService.sync_user_movie_to_tmdb(instance)

@receiver(post_delete, sender=UserMovie)
def on_user_movie_deleted(sender, instance, **kwargs):
    """При удалении UserMovie — убираем из TMDB watchlist/favorite."""
    from vault.services.tmdb_writeback_service import TmdbWritebackService
    TmdbWritebackService.sync_user_movie_deleted(instance)
```

**Регистрация в `vault/apps.py`:**
```python
class VaultConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vault'

    def ready(self):
        import vault.signals  # noqa: F401
```

**Преимущества:**
- Единая точка перехвата для ВСЕХ мутаций (API + legacy views + management commands + import_kinorium_csv)
- Не нужно менять существующий код MovieStatusService
- Автоматически покрывает все 14 точек мутации

**Недостатки:**
- Сигнал срабатывает ВНУТРИ транзакции (нужно `transaction.on_commit`)
- Нужно быть осторожным с производительностью

### 4.2 Вариант B: Модификация MovieStatusService

Добавить вызов `TmdbWritebackService` в каждый метод `MovieStatusService`:

```python
# vault/services/movie_status_service.py

@classmethod
@transaction.atomic
def set_status(cls, user, movie, status_key):
    user_movie = cls._get_or_create_user_movie(user, movie)
    # ... существующая логика ...
    user_movie.save(...)

    # НОВОЕ: write-back
    transaction.on_commit(
        lambda: TmdbWritebackService.sync_user_movie_to_tmdb(user_movie)
    )
```

**Преимущества:**
- Явный контроль (видно где происходит write-back)
- Можно передать context (откуда вызвано)

**Недостатки:**
- Нужно менять 8+ методов в MovieStatusService
- Legacy views (views.py) не покрываются

### 4.3 Вариант C: Гибридный (рекомендуемый)

1. **Django Signals** для автоматического перехвата всех мутаций
2. **`transaction.on_commit`** для гарантии что данные сохранены
3. **Флаг `tmdb_writeback_enabled`** в UserPreferences для глобального выключения
4. **Флаг `tmdb_writeback_disabled_for_movie`** для отключения per-movie

---

## 5. Очередь фоновых задач

### 5.1 Проблема

TMDB API имеет rate limit ~40 req/sec. При массовых операциях (import_kinorium_csv, bulk toggle) нужно ставить write-back в очередь.

### 5.2 Решение: HUEY-задача

```python
# vault/services/tmdb_writeback_queue.py

from huey import crontab
from huey.contrib.djhuey import HUEY

@HUEY.task()
def tmdb_writeback_task(user_movie_id: int, action: str):
    """Фоновая write-back задача."""
    from vault.services.tmdb_writeback_service import TmdbWritebackService
    TmdbWritebackService.execute_writeback(user_movie_id, action)

@HUEY.task()
def tmdb_writeback_bulk_task(user_id: int):
    """Массовая синхронизация всех UserMovie."""
    from vault.services.tmdb_writeback_service import TmdbWritebackService
    TmdbWritebackService.sync_all_user_movies(user_id)
```

### 5.3 Стратегия очереди

```
Изменение UserMovie
    │
    ├── Если tmdb_sync_enabled=False → пропустить
    ├── Если нет tmdb_id у фильма → пропустить
    ├── Если нет write token → пропустить
    │
    ├── Если bulk операция (import, bulk toggle) → tmdb_writeback_bulk_task
    │
    └── Если единичное действие → tmdb_writeback_task
        │
        ├── При success → логируем
        ├── При 429 (rate limit) → retry через retry_after
        ├── При 401 (token expired) → логируем + уведомление
        └── При ошибке → retry 3 раза с exponential backoff
```

---

## 6. Обработка ошибок

### 6.1 HTTP 429 (Rate Limit)

```python
try:
    result = tmdb_api_call()
except TMDbAPIs429Exception:
    # Экспоненциальный backoff: 1s, 2s, 4s, 8s, 16s
    retry_delay = min(2 ** attempt, 60)
    tmdb_writeback_task.schedule(args=(...), delay=retry_delay)
```

### 6.2 HTTP 401 (Unauthorized / Token Expired)

```python
except TMDbAPIs401Exception:
    # Токен истёк — нужно переавторизоваться
    # 1. Логируем ошибку
    # 2. Уведомляем пользователя (web_logger)
    # 3. НЕ пытаемся повторить автоматически
    logger.error("TMDB write token expired. Re-auth required.")
```

### 6.3 Ошибки сети

```python
except (ConnectionError, Timeout):
    # Retry через 30 секунд, до 3 попыток
    if attempt < 3:
        tmdb_writeback_task.schedule(args=(...), delay=30)
```

### 6.4 Логирование

Все write-back операции логируются в `logs/tmdb_writeback.log`:
```
2026-08-23 12:00:00 | SYNC | movie=12345 | tmdb_id=67890 | action=watchlist_add | OK
2026-08-23 12:00:01 | SYNC | movie=12345 | tmdb_id=67890 | action=rate(8) | OK
2026-08-23 12:00:02 | ERROR | movie=11111 | tmdb_id=22222 | action=favorite_add | 429 RATE_LIMITED | retry=5s
```

---

## 7. Авторизация

### 7.1 Текущий flow (без изменений)

```
tmdb_start()  → request_token → пользователь Approve
tmdb_approve() → write_access_token → сохраняется в UserPreferences
```

### 7.2 Проверка токена перед write-back

```python
def _ensure_write_token():
    """Проверить наличие и валидность write token."""
    prefs = UserPreferences.get()
    if not prefs.tmdb_v4_authenticated_access_token:
        raise TmdbWritebackDisabled("No TMDB write token. Authenticate first.")
    return prefs.tmdb_v4_authenticated_access_token
```

### 7.3 Автоматическая проверка валидности

```python
def _validate_token(tmdb_client) -> bool:
    """Попробовать вызвать account() для проверки токена."""
    try:
        tmdb_client.account()
        return True
    except TMDbAPIs401Exception:
        return False
```

---

## 8. Новые модели / поля

### 8.1 Дополнительные поля в UserPreferences

```python
# moviefilter/models.py — UserPreferences

tmdb_writeback_enabled = models.BooleanField(
    'Обратная синхронизация в TMDB',
    default=True,
    help_text='Автоматически записывать изменения статуса/оценки/избранного в TMDB'
)

tmdb_writeback_lists_enabled = models.BooleanField(
    'Синхронизация списков с TMDB',
    default=True,
    help_text='Синхронизировать пользовательские списки с TMDB Lists'
)
```

### 8.2 Новое поле в UserList

```python
# vault/models.py — UserList

tmdb_list_id = models.PositiveIntegerField(
    'TMDB List ID',
    null=True,
    blank=True,
    help_text='ID соответствующего списка на TMDB'
)
```

### 8.3 Новое поле в Movie (опционально, для отладки)

```python
# vault/models.py — Movie (уже есть tmdb_id)

tmdb_writeback_last_at = models.DateTimeField(
    'Последняя write-back синхронизация',
    null=True,
    blank=True
)
```

---

## 9. API эндпоинты (новые)

### 9.1 Ручная синхронизация одного фильма

```python
# vault/api.py

@api.post("/movies/{slug}/tmdb-writeback", response=WritebackResultOut)
def movie_tmdb_writeback(request, slug: str):
    """Принудительно синхронизировать фильм с TMDB (write-back)."""
    ...
```

### 9.2 Полная синхронизация всех фильмов

```python
@api.post("/tmdb-writeback/sync-all", response=BulkWritebackResultOut)
def tmdb_writeback_sync_all(request):
    """Полная синхронизация всех UserMovie с TMDB."""
    ...
```

### 9.3 Статус write-back

```python
@api.get("/tmdb-writeback/status", response=WritebackStatusOut)
def tmdb_writeback_status(request):
    """Статус write-back: сколько синхронизировано, ошибки."""
    ...
```

### 9.4 Управление настройками write-back

```python
@api.patch("/tmdb-writeback/settings", response=WritebackSettingsOut)
def tmdb_writeback_settings(request, payload: WritebackSettingsIn):
    """Включить/выключить write-back."""
    ...
```

---

## 10. Фронтенд

### 10.1 Страница TMDB Auth (`front/src/routes/tmdb/+page.svelte`)

Добавить:
- Статус write token (активен / истёк / не получен)
- Кнопка "Re-authenticate" если токен истёк
- Флаг `tmdb_writeback_enabled` (toggle)
- Флаг `tmdb_writeback_lists_enabled` (toggle)

### 10.2 Страница фильма (`front/src/routes/(vault)/movies/[slug]/+page.svelte`)

Добавить:
- Индикатор синхронизации с TMDB (synced / pending / error)
- Кнопка "Force TMDB write-back"
- Отображение ошибок write-back

### 10.3 Страница списков

Добавить:
- Кнопка "Sync list to TMDB" для каждого UserList
- Отображение TMDB List ID
- Индикатор синхронизации

### 10.4 Preferences (`front/src/routes/preferences/+page.svelte`)

Добавить:
- Toggle `tmdb_writeback_enabled`
- Toggle `tmdb_writeback_lists_enabled`
- Статистика write-back (сколько синхронизировано, ошибок)

---

## 11. Пошаговый план реализации

### Фаза 1: Инфраструктура (2-3 дня)

| # | Задача | Файлы |
|---|--------|-------|
| 1.1 | Добавить поля `tmdb_writeback_enabled`, `tmdb_writeback_lists_enabled` в UserPreferences | `moviefilter/models.py`, `moviefilter/migrations/` |
| 1.2 | Создать `vault/services/tmdb_writeback_service.py` с базовым классом | `vault/services/tmdb_writeback_service.py` |
| 1.3 | Реализовать методы `sync_watch_status`, `sync_favorite`, `sync_rating` | `vault/services/tmdb_writeback_service.py` |
| 1.4 | Добавить поле `tmdb_list_id` в UserList | `vault/models.py`, `vault/migrations/` |
| 1.5 | Создать `vault/signals.py` с post_save/post_delete хуками | `vault/signals.py` |
| 1.6 | Активировать сигналы в `vault/apps.py` | `vault/apps.py` |
| 1.7 | Добавить логирование write-back операций | `vault/services/tmdb_writeback_service.py` |

### Фаза 2: Core write-back (3-4 дня)

| # | Задача | Файлы |
|---|--------|-------|
| 2.1 | Реализовать `sync_user_movie_to_tmdb` — главный метод | `vault/services/tmdb_writeback_service.py` |
| 2.2 | Реализовать `sync_user_movie_deleted` — cleanup при удалении | `vault/services/tmdb_writeback_service.py` |
| 2.3 | Реализовать `create_tmdb_list`, `delete_tmdb_list` | `vault/services/tmdb_writeback_service.py` |
| 2.4 | Реализовать `sync_user_list_add`, `sync_user_list_remove` | `vault/services/tmdb_writeback_service.py` |
| 2.5 | Обработка 429 rate limit с exponential backoff | `vault/services/tmdb_writeback_service.py` |
| 2.6 | Обработка 401 token expired | `vault/services/tmdb_writeback_service.py` |
| 2.7 | Интеграция с HUEY для фоновых задач | `vault/services/tmdb_writeback_queue.py` |

### Фаза 3: Точки мутации (2-3 дня)

| # | Задача | Файлы |
|---|--------|-------|
| 3.1 | Подключить signals к UserMovie (post_save, post_delete) | `vault/signals.py` |
| 3.2 | Подключить signals к UserListMovie (post_save, post_delete) | `vault/signals.py` |
| 3.3 | Добавить `transaction.on_commit` для безопасности | `vault/signals.py` |
| 3.4 | Исключить management commands из write-back (import_kinorium_csv) | `vault/services/tmdb_writeback_service.py` |
| 3.5 | Добавить флаг `_in_bulk_import` для подавления write-back | `vault/services/tmdb_writeback_service.py` |

### Фаза 4: API + Фронтенд (2-3 дня)

| # | Задача | Файлы |
|---|--------|-------|
| 4.1 | Добавить API эндпоинты write-back | `vault/api.py` |
| 4.2 | Обновить страницу TMDB Auth (write token status) | `front/src/routes/tmdb/+page.svelte` |
| 4.3 | Обновить страницу фильма (sync indicator) | `front/src/routes/(vault)/movies/[slug]/+page.svelte` |
| 4.4 | Обновить Preferences (writeback toggles) | `front/src/routes/preferences/+page.svelte` |
| 4.5 | Добавить страницу статуса write-back | `front/src/routes/tmdb-writeback/+page.svelte` |

### Фаза 5: Тестирование (2-3 дня)

| # | Задача |
|---|--------|
| 5.1 | Unit-тесты для TmdbWritebackService |
| 5.2 | Интеграционные тесты с реальным TMDB API (sandbox) |
| 5.3 | Тест rate limit handling |
| 5.4 | Тест token expiry handling |
| 5.5 | Тест bulk import (подавление write-back) |
| 5.6 | Ручное тестирование на реальных данных |

---

## 12. Ключевые архитектурные решения

### Решение 1: Синхронный vs Асинхронный write-back

**Выбор: Синхронный с fallback на async.**

- Единичные операции (toggle status, rate) — **синхронно** через `transaction.on_commit`
- При ошибке сети/429 — **асинхронный retry** через HUEY
- Bulk операции (import) — **только асинхронно** через HUEY

### Решение 2: Куда девать bulk import

**Выбор: Глобальный флаг `_bulk_import_in_progress`.**

```python
class TmdbWritebackService:
    _bulk_import_in_progress = False

    @classmethod
    def sync_user_movie_to_tmdb(cls, user_movie):
        if cls._bulk_import_in_progress:
            return WritebackResult(success=False, action="skipped", ...)
        # ...
```

Import-команда устанавливает флаг:
```python
TmdbWritebackService._bulk_import_in_progress = True
# ... import ...
TmdbWritebackService._bulk_import_in_progress = False
# ... или drain queue ...
```

### Решение 3: Concurrency (множественные вызовы)

**Выбор: Batch в HUEY.**

При массовых операциях HUEY дедуплицирует задачи:
- Если UserMovie A изменяется 3 раза за 5 секунд → только 1 write-back
- Реализация через `TaskLock` или `delay` в HUEY

### Решение 4: Offline / TMDB недоступен

**Выбор: Retry queue + manual sync.**

- Если TMDB недоступен → задача ставится в retry queue (до 24 часов)
- На UI показывается "Pending sync" индикатор
- Кнопка "Force sync all" для ручного триггера

---

## 13. Безопасность

1. **Write token** хранится в `UserPreferences.tmdb_v4_authenticated_access_token` — зашифровать? (пока нет, single-user)
2. **Нет JWT/session-based auth для TMDB** — используется нативный OAuth V4 flow
3. **Rate limiting** — TMDB лимит ~40 req/sec, наш лимит ~1 req/sec (保守)
4. **Idempotency** — все write-back операции должны быть идемпотентны (можно повторять безопасно)

---

## 14. Метрики и мониторинг

### 14.1 Логи
- `logs/tmdb_writeback.log` — все write-back операции
- `logs/error.log` — ошибки write-back

### 14.2 Метрики (через API)
- Всего синхронизаций
- Успешных / Ошибочных
- Последняя синхронизация
- Ожидающие retry

### 14.3 Уведомления
- Token expired → уведомление на UI
- Too many errors → уведомление на UI

---

## 15. Risks и Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Rate limit TMDB (429) | Write-back блокируется | Exponential backoff, batch queue |
| Token expiry (401) | Write-back невозможен | Auto-detect + notification + re-auth flow |
| Сеть недоступна | Write-back не проходит | Retry queue (24h), manual sync |
| Bulk import затмевает write-back | UI фризит | Bulk flag + async processing |
| Двойная запись (Vault + TMDB одновременно) | Race condition | Single-user assumption = нет concurrency |
| TMDB API downtime | Write-back queued | HUEY retry, persistent queue |

---

## 16. Файлы для изменения (сводка)

| Файл | Тип изменения |
|------|---------------|
| `moviefilter/models.py` | Новые поля в UserPreferences |
| `vault/models.py` | Новое поле `tmdb_list_id` в UserList |
| `vault/signals.py` | **НОВЫЙ** — Django signals |
| `vault/apps.py` | Активация signals |
| `vault/services/tmdb_writeback_service.py` | **НОВЫЙ** — основной сервис |
| `vault/services/tmdb_writeback_queue.py` | **НОВЫЙ** — HUEY задачи |
| `vault/services/movie_status_service.py` | Нет изменений (сигналы покрывают) |
| `vault/api.py` | Новые эндпоинты |
| `front/src/routes/tmdb/+page.svelte` | Write token status |
| `front/src/routes/(vault)/movies/[slug]/+page.svelte` | Sync indicator |
| `front/src/routes/preferences/+page.svelte` | Writeback toggles |
| `front/src/routes/tmdb-writeback/+page.svelte` | **НОВЫЙ** — статус write-back |
| `vault/migrations/` | Новые миграции |

---

## 17. Зависимости

- **tmdbapis** — уже установлена (v1.2.30), все write-методы доступны
- **HUEY** — уже используется для TMDB sync queue
- **Django signals** — встроены в Django, не требуют дополнительных зависимостей
- **threading.Lock** — уже используется в client_singleton.py

---

## 18. Порядок приоритетов для реализации

1. **P0 (Critical):** write-back для `watch_status` + `is_favorite` + `rating`
2. **P1 (High):** write-back для пользовательских списков (TMDB Lists)
3. **P2 (Medium):** bulk sync all + UI статус
4. **P3 (Low):** рейтинги сезонов/эпизодов
5. **P4 (Future):** pull from TMDB (read changes made directly on TMDB website)

---

# ЧАСТЬ 2: ТЕХНИЧЕСКАЯ СПРАВКА ДЛЯ АГЕНТА

> Эта секция содержит конкретные сигнатуры, пути, паттерны и примеры кода.
> Агент должен использовать её как reference при реализации.

---

## A. Точки мутации (ВСЕ места, где меняется UserMovie)

### A1. MovieStatusService — 8 методов

Все файлы: `vault/services/movie_status_service.py`

| # | Метод | Строка | Что меняет | tmdbapi action |
|---|-------|--------|------------|----------------|
| 1 | `set_status(user, movie, 'watched')` | :67 | `watch_status=WATCHED` | `remove_from_watchlist` |
| 2 | `set_status(user, movie, 'will_watch')` | :67 | `watch_status=PLAN` | `add_to_watchlist` |
| 3 | `set_status(user, movie, 'wont_watch')` | :67 | `watch_status=SKIP` | `remove_from_watchlist` |
| 4 | `set_status(user, movie, 'favorites')` | :75 | `is_favorite=True` | `mark_as_favorite` |
| 5 | `unset_status(user, movie, ...)` | :103 | `watch_status=None` или `is_favorite=False` | `remove_from_watchlist` / `remove_as_favorite` |
| 6 | `_cleanup_user_movie(user_movie)` | :24 | `DELETE entire row` | `remove_from_watchlist` + `remove_as_favorite` + `delete_rating` |
| 7 | `rate_movie(user, movie, value)` | :152 | `rating=N, watch_status=WATCHED` | `rate(N)` + `remove_from_watchlist` |
| 8 | `remove_rating(user, movie)` | :169 | `rating=None` | `delete_rating` |

### A2. API прямые мутации — toggle-list

Файл: `vault/api.py`, строка 1030-1054

```python
# POST /movies/{slug}/toggle-list
# Добавление:  UserListMovie.objects.create(user_list=user_list, movie=movie)  # строка 1047
# Удаление:    relation.delete()  # строка 1044
```

### A3. Legacy views — add_to_list / remove_from_list

Файл: `vault/views.py`
- `add_to_list` — строка 769-787 (UserListMovie.get_or_create)
- `remove_from_list` — строка 790-809 (UserListMovie.delete)

### A4. SeasonStatusService

Файл: `vault/services/season_status_service.py`
- `set_season_status` — строка 60-88 (UserSeason.save)
- `sync_statuses_from_user_movie` — строка 90-115 (UserSeason.get_or_create)

### A5. Management command import_kinorium_csv

Файл: `vault/management/commands/import_kinorium_csv.py`
- Строки 298, 273, 280, 313, 321, 341, 325, 468 — mass UserMovie mutations

**КРИТИЧЕСКИ ВАЖНО:** Все эти мутации ДОЛЖНЫ быть покрыты write-back через сигналы.
Management command ДОЛЖЕН устанавливать `TmdbWritebackService._bulk_import_in_progress = True`.

---

## B. Как получить TMDB-клиент для write-back

```python
from tmdb_adapter.client_singleton import get_tmdb_client

tmdb = get_tmdb_client()  # TMDbAPIs instance

# Клиент уже настроен с v4_write_token → автоматически создаёт v3 session_id
# Все write-методы работают через v3 API под капотом
```

**Клиент — синглтон** (`tmdb_adapter/client_singleton.py:14`). Повторные вызовы `get_tmdb_client()` возвращают тот же инстанс. Токен обновляется автоматически при смене.

---

## C. Конкретные tmdbapis методы для write-back

### C1. Watchlist

```python
movie_obj = tmdb.movie(tmdb_id)     # Movie object
tv_obj = tmdb.tv_show(tmdb_id)      # TVShow object

# Добавить в watchlist
movie_obj.add_to_watchlist()         # V3 API: POST /account/{id}/watchlist
tv_obj.add_to_watchlist()

# Убрать из watchlist
movie_obj.remove_from_watchlist()
tv_obj.remove_from_watchlist()
```

### C2. Favorites

```python
# Добавить в избранное
movie_obj.mark_as_favorite()         # V3 API: POST /account/{id}/favorite
tv_obj.mark_as_favorite()

# Убрать из избранного
movie_obj.remove_as_favorite()
tv_obj.remove_as_favorite()
```

### C3. Ratings

```python
# Поставить оценку (0.5 - 10.0, шаг 0.5)
movie_obj.rate(8.5)                  # V3 API: POST /movie/{id}/rating
tv_obj.rate(9.0)

# Удалить оценку
movie_obj.delete_rating()            # V3 API: DELETE /movie/{id}/rating
tv_obj.delete_rating()
```

### C4. Custom Lists (V4 API)

```python
api4 = tmdb._api4  # Получить доступ к V4 API

# Создать список
result = tmdb.create_list(
    name="My List",
    iso_639_1="ru",
    description="Описание",
    public=True
)
new_list_id = result.id  # или int если load=False

# Добавить элементы (batch)
api4.list_add_items(list_id=12345, items=[
    {"media_type": "movie", "media_id": 550},
    {"media_type": "tv", "media_id": 1396},
])

# Удалить элементы (batch)
api4.list_remove_items(list_id=12345, items=[
    {"media_type": "movie", "media_id": 550},
])

# Удалить список
api4.list_delete_list(list_id=12345)
```

### C5. Определение media_type из Movie

```python
# Movie.tmdb_media_type хранит "movie" или "tv"
# Для tmdbapis нужен объект Movie или TVShow:

if movie.tmdb_media_type == "movie":
    tmdb_obj = tmdb.movie(movie.tmdb_id)
else:
    tmdb_obj = tmdb.tv_show(movie.tmdb_id)
```

---

## D. Обработка ошибок tmdbapis

```python
from tmdbapis.exceptions import (
    TMDbAPIsException,     # базовый
    Authentication,        # 401 — нет авторизации
    TMDbAPIs404Exception,  # 404
    TMDbAPIs429Exception,  # 429 rate limit
)
```

**Конкретный паттерн:**

```python
try:
    movie_obj.add_to_watchlist()
except TMDbAPIs429Exception:
    # Rate limit — retry через N секунд
    logger.warning("TMDB 429 rate limited, retrying in 5s")
    raise  # HUEY задача перепланирует
except Authentication:
    # Token expired
    logger.error("TMDB token expired, re-auth required")
except TMDbAPIsException as exc:
    logger.error(f"TMDB API error: {exc}")
```

---

## E. HUEY — паттерн задач в проекте

Файл: `movie_filter_pro/huey.py` — `HUEY = SqliteHuey(filename=...)`

Файл: `vault/tasks.py` — существующие задачи

```python
from movie_filter_pro.huey import HUEY

@HUEY.task()
def my_task(arg1: int, arg2: str):
    # Выполняется асинхронно
    return result

# Планирование с задержкой:
my_task.schedule(args=(1, "hello"), delay=5)  # через 5 секунд
```

**Для write-back задач:**

```python
# vault/tasks.py — добавить:

@HUEY.task()
def tmdb_writeback_user_movie(user_movie_id: int):
    """Write-back одного UserMovie."""
    from vault.services.tmdb_writeback_service import TmdbWritebackService
    user_movie = UserMovie.objects.select_related('movie').get(pk=user_movie_id)
    TmdbWritebackService.sync_user_movie_to_tmdb(user_movie)

@HUEY.task()
def tmdb_writeback_sync_all():
    """Полная синхронизация."""
    from vault.services.tmdb_writeback_service import TmdbWritebackService
    TmdbWritebackService.sync_all_user_movies()
```

---

## F. Django Signals — паттерн

### F1. Создать `vault/signals.py`

```python
import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction

from vault.models import UserMovie, UserListMovie

logger = logging.getLogger("vault.tmdb_writeback")


@receiver(post_save, sender=UserMovie)
def on_user_movie_saved(sender, instance, created, **kwargs):
    from vault.services.tmdb_writeback_service import TmdbWritebackService
    if TmdbWritebackService.is_bulk_import_in_progress():
        return
    # on_commit гарантирует что транзакция завершена
    transaction.on_commit(
        lambda: TmdbWritebackService.sync_user_movie_to_tmdb(instance)
    )


@receiver(post_delete, sender=UserMovie)
def on_user_movie_deleted(sender, instance, **kwargs):
    from vault.services.tmdb_writeback_service import TmdbWritebackService
    if TmdbWritebackService.is_bulk_import_in_progress():
        return
    transaction.on_commit(
        lambda: TmdbWritebackService.sync_user_movie_deleted(instance)
    )


@receiver(post_save, sender=UserListMovie)
def on_user_list_movie_saved(sender, instance, created, **kwargs):
    if not created:
        return
    from vault.services.tmdb_writeback_service import TmdbWritebackService
    if TmdbWritebackService.is_bulk_import_in_progress():
        return
    transaction.on_commit(
        lambda: TmdbWritebackService.sync_list_item_added(instance)
    )


@receiver(post_delete, sender=UserListMovie)
def on_user_list_movie_deleted(sender, instance, **kwargs):
    from vault.services.tmdb_writeback_service import TmdbWritebackService
    if TmdbWritebackService.is_bulk_import_in_progress():
        return
    transaction.on_commit(
        lambda: TmdbWritebackService.sync_list_item_removed(instance)
    )
```

### F2. Активировать в `vault/apps.py`

```python
class VaultConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vault'
    verbose_name = 'Фильмотека'

    def ready(self):
        import vault.signals  # noqa: F401
```

---

## G. API — паттерн эндпоинтов

Файл: `vault/api.py`

### G1. Схемы (Schema)

```python
from ninja import Schema

class WritebackResultOut(Schema):
    success: bool
    action: str
    tmdb_id: int | None = None
    media_type: str | None = None
    error: str | None = None

class WritebackStatusOut(Schema):
    writeback_enabled: bool
    lists_writeback_enabled: bool
    write_token_present: bool
    total_user_movies: int
    synced_count: int
    pending_count: int
    error_count: int

class WritebackSettingsIn(Schema):
    writeback_enabled: bool | None = None
    lists_writeback_enabled: bool | None = None
```

### G2. Эндпоинт

```python
@api.post("/movies/{slug}/tmdb-writeback", response=WritebackResultOut)
def movie_tmdb_writeback(request, slug: str):
    movie = Movie.objects.filter(slug=slug).first()
    if movie is None:
        raise HttpError(404, "Movie not found")

    user = _require_api_user(request)

    user_movie = UserMovie.objects.filter(user=user, movie=movie).first()
    if user_movie is None:
        raise HttpError(404, "No user movie data")

    from vault.services.tmdb_writeback_service import TmdbWritebackService
    result = TmdbWritebackService.sync_user_movie_to_tmdb(user_movie)

    return WritebackResultOut(
        success=result.success,
        action=result.action,
        tmdb_id=result.tmdb_id,
        media_type=result.media_type,
        error=result.error,
    )
```

---

## H. Frontend — паттерн API-вызовов

Файл: `front/src/routes/(vault)/movies/[slug]/+page.svelte`

```svelte
<script lang="ts">
  const runWriteback = async () => {
    const response = await fetch(`/api/vault/movies/${movie.slug}/tmdb-writeback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });

    const payload = await response.json();

    if (!response.ok) {
      toast.error(payload.message ?? `HTTP ${response.status}`);
      return;
    }

    if (payload.success) {
      toast.success(`TMDB: ${payload.action}`);
    } else {
      toast.error(`TMDB error: ${payload.error}`);
    }
  };
</script>
```

---

## I. Новые поля моделей — конкретные изменения

### I1. UserPreferences (`moviefilter/models.py`)

Добавить после строки 182 (`tmdb_sync_delay_seconds`):

```python
tmdb_writeback_enabled = models.BooleanField(
    'Обратная синхронизация в TMDB',
    default=True,
)
tmdb_writeback_lists_enabled = models.BooleanField(
    'Синхронизация списков с TMDB',
    default=True,
)
```

### I2. UserList (`vault/models.py`)

Добавить после существующих полей (строка ~467):

```python
tmdb_list_id = models.PositiveIntegerField(
    'TMDB List ID',
    null=True,
    blank=True,
)
```

---

## J. Миграции

```bash
# После изменения моделей:
uv run python manage.py makemigrations moviefilter vault
uv run python manage.py migrate
```

---

## K. Логирование

```python
import logging

# В tmdb_writeback_service.py:
logger = logging.getLogger("vault.tmdb_writeback")

# В settings.py ДОБАВИТЬ (если нет):
LOGGING = {
    'loggers': {
        'vault.tmdb_writeback': {
            'handlers': ['file', 'console'],
            'level': 'DEBUG',
        },
    },
}
```

---

## L. Чеклист для агента

- [ ] Прочитать `vault/services/movie_status_service.py` — понять все 8 методов мутации
- [ ] Прочитать `vault/api.py` строки 1010-1054 — toggle-status и toggle-list
- [ ] Прочитать `tmdb_adapter/client_singleton.py` — как получить TMDB клиент
- [ ] Прочитать `tmdb_adapter/auth.py` — как работает OAuth flow
- [ ] Прочитать `movie_filter_pro/huey.py` — как устроен HUEY
- [ ] Прочитать `vault/tasks.py` — паттерн HUEY задач
- [ ] Прочитать `vault/apps.py` — как активировать signals
- [ ] Прочитать `moviefilter/models.py` строки 134-206 — UserPreferences
- [ ] Прочитать `vault/models.py` строки 404-487 — UserMovie, UserList
- [ ] Проверить `front/src/lib/components/ui/` — какие shadcn-svelte компоненты доступны
- [ ] Перед bulk import установить `TmdbWritebackService._bulk_import_in_progress = True`
- [ ] Все write-back вызовы оборачивать в try/except с обработкой TMDB ошибок
- [ ] Использовать `transaction.on_commit` в signals (не вызывать write-back внутри транзакции)
- [ ] Не ломать существующий MovieStatusService — сигналы перехватывают автоматически
