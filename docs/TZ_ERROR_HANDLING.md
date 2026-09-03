# ТЗ: Обработка ошибок синхронизации Vault ↔ TMDB

> Статус: утверждено 2026-09-03. Вынесено из `PLAN_SYNC_OPTIMIZATION.md:R6d`.
> Решения: `3` подряд фейла = стоп, `5` попыток для транзиентной, стоп обеих очередей на `401`, лог+бейдж без тоста.

## 1) Проблема сейчас

- Нет разделения критичных (`401` протух токен) и ретрабельных (`429`, `500`, `timeout`, `not_found`).
- `401` сейчас не останавливает очередь — падает в `persistent queue` и копится.
- Идея «остановить если очередь >1000» не ловит ранний сигнал: `5` фильмов подряд с ошибкой уже значит что-то сломано (сеть легла, TMDB лежит, токен слетел).
- Нет счётчика `success/fail/retry` каждые `100` фильмов для наблюдения.

## 2) Цели ТЗ

- Один фильм с бизнес-ошибкой (`not_found`, `needs_confirmation`) не должен стопать bulk. Bulk стопается только когда проблема системная и массовая.
- Критичная ошибка останавливает обе очереди сразу и требует ручного вмешательства.
- Ретрабельная ошибка — тихий backoff без спама.

## 3) Классификация ошибок

| Категория | Примеры | Как определяем | Поведение |
|-----------|---------|----------------|-----------|
| **Критичная (stop now)** | `401 Unauthorized`, `403 WritePermission`, `PrivateResource`, `Invalid API key` | `TmdbWritebackService._is_auth_error()` / `status_code==401` | Стоп bulk: `UserPreferences.tmdb_sync_enabled=False`, `TMDBSyncQueueItem` не берём новые, `TMDBWritebackQueueItem` → `state=ERROR, next_retry=None`. Лог `CRITICAL`, UI бейдж «Требуется re-auth». Ручной рестарт только после `reauth`. |
| **Лимит (backoff)** | `429 Rate limit` | `_is_rate_limited()` / `429` в строке | Не стопаем. `next_retry_at` по лестнице `10/30/60/120/300` сек (уже реализовано в `6b`). Перед каждым `tmdb.*` — `TmdbRateLimiter.wait() 0.5 сек`. |
| **Транзиентная (retry)** | `500`, `502`, `503`, `timeout`, `ConnectionError` | `status_code 5xx` или `Timeout`/`Connection` в строке | Ретрай до `5` попыток с backoff `600 сек` (как сейчас для прочих). После `5` → `state=ERROR` без `next_retry`, требует ручной `Retry` в UI. Считается в «3 подряд фейлы». |
| **Бизнес (no retry)** | `not_found`, `needs_confirmation`, `TMDB ID не найден` | `SyncStatus` `not_found`/`confirm` из `TMDBMovieSyncService` | Не ретрай, не ошибка очереди. `queue state=NOT_FOUND/CONFIRM`, фильм пропускается. Не влияет на стоп-кран. |

## 4) Стоп-кран для bulk (утверждено)

Bulk стопается **только** по двум условиям, остальное — тихие ретраи:

1. **Критичная ошибка на любом фильме** → стоп сразу обеих очередей (read + write) (п.3).
2. **3 подряд транзиентных/лимит фейлов** (подряд без `success`/`business` между ними) → стоп. Счётчик `consecutive_failures` в памяти процесса синка (сбрасывается на каждом `synced`/`not_found`/`confirm`). При `>=3` → `stop()` + лог `BULK_STOP | reason=3_consecutive_failures | last_errors=[...]`.

Почему `3`, а не `1000`: `3` — ранний сигнал что `TMDB` лежит или сеть упала, нет смысла гнать `10K` в ошибку. `1000` заметим через час.

**Что не стопает:** одиночные `500` раз в `50` фильмов, `not_found`, `confirm`.

## 5) Счётчик и логи (наблюдаемость)

- В `TMDBSyncQueueService` завести `bulk_stats = {success, not_found, confirm, retry_transient, rate_limited, critical}`.
- Лог каждые `100` фильмов: `BULK_PROGRESS | done=300/10000 | success=240 | not_found=20 | confirm=10 | retry=30 | rate=15`.
- При стоп-кране — `BULK_STOP` с последними `5` `last_error`.

## 6) Где править (когда утвердим)

- `vault/services/tmdb_movie_sync_service.py` — пробрасывать категорию ошибки в `TMDBSyncResult` (сейчас `error` строка).
- `vault/services/tmdb_sync_queue_service.py` — `process_one()` ведёт `consecutive_failures`, вызывает `stop()` по п.4, пишет `bulk_stats`.
- `vault/services/tmdb_writeback_service.py` — уже делит `401` vs `429` vs прочие; добавить `5xx` в транзиентные, маппить в `next_retry`.
- `vault/tasks.py` — `tmdb_sync_tick` / `person_sync_tick` читают `tmdb_sync_enabled` перед взятием следующего.
- `vault/api.py` + `front/src/routes/tmdb-sync` — показать `bulk_stats` и причину стопа.
- `docs/WRITEBACK_IMPLEMENTATION.md` — секция `6.8` после утверждения.

## 7) Решения по вопросам (2026-09-03)

1. `3 подряд` транзиентных/`429` → стоп (считаем `429` тоже, т.к. системная).
2. `5` попыток для транзиентной — утверждено.
3. Стопать обе очереди при `401` — утверждено.
4. Достаточно лога + бейджа, тост не нужен.

## 8) Реализация

- `6a/b` — `vault/services/tmdb_rate_limiter.py`, `tmdb_writeback_service._get_retry_delay` уже готово.
- Следующий шаг — `consecutive_failures=3`, `bulk_stats` каждые `100`, `5` попыток лимит, стоп обеих очередей (см. `vault/services/tmdb_sync_queue_service.py`, `vault/services/tmdb_writeback_service.py`).
