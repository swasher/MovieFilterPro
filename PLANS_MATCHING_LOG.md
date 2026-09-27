# PLANS_MATCHING_LOG.md — Подробный лог матчинга на клиенте

## Цель

Система матчинга фильмов с TMDB использует многоступенчатый pipeline: поиск по API, скоринг кандидатов, веб-поиск (SearXNG/Tavily), несколько LLM-сервисов (GROQ, локальный AI). Сейчас пользователь видит только конечный результат в виде тоста (успех / ошибка / нужен выбор).

**Задача**: добавить детальный лог на клиенте, чтобы в реальном времени видеть, что происходит на каждом шаге матчинга. Например:

- `[Матчинг]` «Голодные игры» / «The Hunger Games» / 2012
- `[TMDB поиск]` query="The Hunger Games", movie → 8 кандидатов
- `[GROQ]` tmdb_id=70160 confidence=0.92 — победитель
- `[Итог]` auto_match → tmdb_id=70160

Это особенно важно при отладке проблемных фильмов (не нашёл, нашёл не то, LLM недоступен и т.д.).

## Оценка текущей архитектуры

### Что уже есть

| Компонент | Что делает | Есть ли лог? |
|---|---|---|
| `tmdb_movie_matching_service.py` | Сбор кандидатов TMDB, скоринг | Нет (только Python `logging`) |
| `tmdb_match_resolver.py` | Pipeline: pre-AI правила → Groq → AI-выбор → AI-verify | Нет (Python `logging`) |
| `tmdb_smart_search_service.py` | Веб-поиск → year-free TMDB → rank → AI | Нет (Python `logging`) |
| `tmdb_groq_matching_service.py` | HTTP-запросы к GROQ, сравнение сюжетов | Нет (Python `logging`) |
| `tmdb_ai_matching_service.py` | Локальный AI-выбор + сверка сюжетов | Нет (Python `logging`) |
| `tmdb_sync_queue_service.py` | Оркестрация тиков HUEY | Нет |
| `web_logger/weblogger.py` | WebSocket-канал (`send_log_to_websocket`, `send_notification`) | **Есть, готов** |
| `front/src/routes/tmdb-sync/+page.svelte` | UI очереди — polling, тосты, таблица | Только тосты |

### Что НЕ хватает

1. **Серверная сторона**: в сервисах матчинга нет ни одного вызова `web_logger`. Весь прогресс идёт только в Python `logging` (файлы `debug.log` / `scan.log`), не в WebSocket.
2. **Клиентская сторона**: `tmdb-sync/+page.svelte` не подключён к WebSocket. Он использует только polling (`setInterval`) и `toast`.
3. **Нет структуры "шаг"**: сейчас `send_log_to_websocket` принимает простую строку. Для красивого UI нужен структурированный payload (тип шага, статус, данные).

### Проблема доставки: InMemoryChannelLayer vs HUEY (решено)

`CHANNEL_LAYERS` использует `InMemoryChannelLayer` (`movie_filter_pro/settings.py`), а bulk-синк
выполняется HUEY-воркером — отдельным процессом (`supervisord.conf`, `Makefile`). События из
воркера через `group_send` в in-memory слой web-процесса не попадают. Scan-лог работает только
потому, что скан живёт в процессе web (asyncio task в `kinozal_scan/runtime.py`).

**Решение**: свой лёгкий мост LISTEN/NOTIFY поверх PostgreSQL (`web_logger/pg_bridge.py`),
подробности — Шаг 0. Отправка match-событий идёт через `publish_notification()`, которая делает
`SELECT pg_notify(...)`; в web-процессе фоновый поток-листенер получает payload и раздаёт его
локальным WebSocket-клиентам через существующий `group_send("log_updates")`.

> [!NOTE]
> Вариант с `channels_postgres` отклонён: его глобальный `AsyncConnectionPool` привязан к event loop,
> а в проекте отправка идёт из синхронных контекстов (HUEY-потоки, sync views) через `async_to_sync`,
> который создаёт новый loop на каждый вызов. Это гарантированно ломает пул. Плюс лишние зависимости
> (`psycopg_pool`, `msgpack`), миграции и внутренние таблицы.

### Вывод: архитектура в целом готова, нужен «последний километр»

WebSocket-канал уже работает (`web_logger`). Нужно:
- добавить мост `pg_bridge` для кросс-процессной доставки (Шаг 0),
- добавить вызовы `web_logger.send_match_log()` в сервисы матчинга,
- подключить WebSocket на отдельной странице `/match-log` и отображать события в UI.

> [!TIP]
> **Лог работает одинаково для bulk и manual sync.**
> Оба режима (очередь HUEY и ручная кнопка «▶» у конкретного фильма) в итоге вызывают один и тот же
> `TMDBMovieSyncService.sync_movie()`, внутри которого живут матчинг и его сервисы
> (`TMDBMovieMatchingService`, `TMDBMatchResolver`, `tmdb_smart_search_service` и т.д.).
> Поэтому события `match_start`/`match_result` ставятся на уровне `sync_movie`
> (в существующие `_log_start`/`_log_done`), а вложенные события — в сервисы матчинга;
> так покрываются и bulk, и manual, и legacy views, и import-флоу.

> **Масштаб**: небольшой-средний. Серверная часть — дописать ~20-30 `send_log` в 5 файлах. Клиентская — добавить `<LogPanel>` компонент и WebSocket-подключение.

---

## Шаги pipeline матчинга (что хотим логировать)

```
TMDBSyncQueueService.process_one()
  └─ TMDBMovieSyncService.sync_movie()
       ├─ [IMDB lookup] TMDBMovieMatchingService.find_by_imdb_id()  -- если есть imdb_id
       │
       └─ [основной] TMDBMovieMatchingService.match_movie()
            ├─ _collect_candidates()        -- поиск в TMDB API (movie_search / tv_search)
            ├─ _enrich_with_alternative_titles()  -- детали топ-кандидатов
            ├─ _build_scored_candidates()   -- скоринг
            │
            ├─ [auto_match] → готово
            ├─ [not_found] → _smart_search_fallback()
            │     └─ tmdb_smart_search_service.smart_search()
            │          ├─ WebSearchService.search_web()   -- SearXNG / Tavily
            │          ├─ TMDBAIMatchingService.extract_web_hints()  -- локальный AI (подсказки)
            │          ├─ collect_candidates()            -- year-free TMDB ru+en
            │          ├─ rank_candidates()
            │          └─ score_candidates()              -- AI сравнение сюжетов
            │
            └─ [needs_*] → TMDBMatchResolver.resolve_with_ai_if_confident()
                 ├─ _apply_pre_ai_rules()   -- дословное совпадение описаний
                 ├─ _stage_groq_if_confident()  -- GROQ HTTP-запросы
                 ├─ _stage_choose()             -- локальный AI-выбор
                 ├─ _stage_verify_plot()         -- локальный AI-верификация
                 └─ _promote_to_auto_match()
```

---

## План реализации

### Шаг 0 — PG-мост для кросс-процессной доставки (backend)

**Новый файл**: `web_logger/pg_bridge.py`

Два независимых механизма:

1. `publish_notification(payload: dict)` — публикация из любого процесса/потока.
   Синхронный `SELECT pg_notify('ws_notifications', %s)` через Django-коннект
   (`json.dumps(..., ensure_ascii=False, default=str)` — защита от Decimal/enum/datetime).
   Payload > ~7900 байт отбрасывается (лимит NOTIFY 8000), событие не должно ронять pipeline.
2. `start_listener_thread()` — идемпотентный daemon-поток с **синхронным psycopg**
   (`conn.notifies()`), reconnect-loop с паузой ~5 сек. На каждый payload —
   `async_to_sync(channel_layer.group_send)("log_updates", {"type": "send_notification", "payload": payload})`,
   дальше работает существующий `LogConsumer`. Синхронный psycopg выбран сознательно: не зависит от
   Windows Proactor/Selector loop policy.

**Старт**: из `movie_filter_pro/asgi.py` (один раз на процесс) + страховочный вызов в
`LogConsumer.connect` (идемпотентно). HUEY-процесс листенер не запускает — ему некому раздавать.

**Транспорт только для match-логов**: `send_notification`/`asend_notification` и scan-путь
(`scan_complete`) не трогаем — они работают в web-процессе и используют прямой `group_send`.

---

### Шаг 1 — Структура лог-событий (backend)

**Файл**: `web_logger/weblogger.py`

Добавить хелпер `send_match_log(event_type, **data)` для структурированных событий матчинга.
Это не ломает существующий `send_notification` — просто удобная обёртка над PG-мостом.

```python
def send_match_log(event_type: str, **data):
    """Структурированное событие шага матчинга → WebSocket (через PG-мост).

    Никогда не бросает исключение: лог не должен ронять pipeline.
    """
    try:
        publish_notification({
            "type": "match_log",
            "event": event_type,
            **data,
        })
    except Exception:
        debug_logger.debug("send_match_log failed", exc_info=True)
```

Новый хелпер экспортировать из `web_logger/__init__.py`.

**Типы событий** (предлагаемые `event_type`):

| event_type | Когда | Поля |
|---|---|---|
| `match_start` | начало обработки фильма | `movie_id`, `title`, `original_title`, `year` |
| `tmdb_search` | один поисковый запрос к TMDB | `query`, `media_type`, `year`, `results_count` |
| `smart_search_start` | начало умного поиска (fallback) | — |
| `web_search` | запрос к SearXNG/Tavily | `engine`, `ok` |
| `ai_web_hints` | локальный AI извлёк подсказки | `clean_title`, `llm_year`, `queries_added` |
| `ai_score` | локальный AI сравнил пару сюжетов в умном поиске | `tmdb_id`, `same_work`, `confidence` |
| `groq_call` | HTTP-запрос к GROQ | `tmdb_id`, `confidence`, `ok` |
| `ai_choose` | локальный AI выбирает кандидата | `selected_tmdb_id`, `confidence` |
| `ai_verify` | локальный AI верифицирует сюжет | `same_work`, `confidence` |
| `literal_match` | дословное совпадение описаний | `tmdb_id` |
| `match_result` | итог для фильма | `status`, `tmdb_id`, `message`, `score` |

---

### Шаг 2 — Вставить `send_match_log` в сервисы

**Затрагиваемые файлы** (каждый — отдельный мини-шаг, тестируем после каждого):

1. **`tmdb_movie_sync_service.py`** — `match_start` в `_log_start`, `match_result` в `_log_done`.
   Это единственная точка, покрывающая bulk (HUEY), manual-кнопку, legacy views и import-флоу.
   `_log_done` получает необязательные kwargs (`movie`, `tmdb_id`, `media_type`, `score`),
   call-sites в `sync_movie` передают то, что есть под рукой. `process_one`
   (`TICK_START`/`TICK_DONE`) не трогаем — это очередь, а не матчинг.
2. **`tmdb_movie_matching_service.py`** — `_search_once` → `tmdb_search` (query, media_type, year, results_count)
3. **`tmdb_smart_search_service.py`** — `smart_search` → `smart_search_start`; `enrich_queries_from_web` → `web_search` + `ai_web_hints`; `score_candidates` → `ai_score`
4. **`tmdb_match_resolver.py`** — `_apply_pre_ai_rules` → `literal_match`; `_stage_choose` → `ai_choose`; `_stage_verify_plot` → `ai_verify`
5. **`tmdb_groq_matching_service.py`** — `choose_confident` (цикл по кандидатам) → `groq_call` (`ok=true/false`), чтобы у каждого события был `tmdb_id`

> [!NOTE]
> Вставки должны быть **только внутри уже существующих методов**, без изменения публичных сигнатур.
> Ошибка в `send_match_log` не должна ронять pipeline — `try/except` уже внутри хелпера (Шаг 1).

---

### Шаг 3 — Отдельная страница лога

**Новый файл**: `front/src/routes/match-log/+page.svelte`

> [!IMPORTANT]
> Лог реализуется как **отдельная страница** (`/match-log`), а не интегрируется в существующие страницы.
> Это упрощает разработку и не затрагивает `tmdb-sync/+page.svelte` и другие страницы.

1. Создать маршрут `front/src/routes/match-log/+page.svelte`.
2. При монтировании открыть WebSocket на `ws://host/ws/log/` (protocol/host считать от `window.location`,
   паттерн автореконнекта — как в `front/src/lib/services/scanLogger.svelte.ts`).
3. Фильтровать сообщения с `payload.type === "match_log"` (consumer пересылает payload как есть),
   пушить в массив событий.
4. Отображать события в виде хронологического лога.

**UX страницы**:
- Авто-скролл к последнему событию.
- Иконка/цвет по типу события (🔍 поиск, 🤖 AI, 🌐 веб, ✅ успех, ❌ ошибка).
- Кнопка «Очистить лог».
- Максимум последних N событий (например, 200), старые вытесняются.
- Лог хранится только в памяти браузера (не персистентный) — при закрытии/перезагрузке обнуляется.

---

### Шаг 4 — Пункт в шапке сайта

**Файл**: `front/src/lib/components/SiteShell.svelte` — user-меню (DropdownMenu с пунктами
Django Admin / События связок / TMDB Sync Queue / TMDB Auth / Write-back Error Log).

Добавить в группу один пункт-ссылку на `/match-log` (например, с иконкой `ScrollText`).

```
[👤 username ▾]
  ├─ ...
  ├─ Match Log       ← новый пункт
  ├─ ...
  └─ Выйти
```

---

### Шаг 5 — WebSocket consumer: роутинг `match_log`

**Файл**: `web_logger/websocket_consumers.py`

Проверить, что существующий consumer корректно транслирует `send_notification` с любым payload на фронт. Скорее всего, ничего менять не нужно.

---

## Порядок работы

1. ~~**Обсудить и согласовать** список событий и поля выше.~~ Согласовано: свой PG-мост, транспорт только для `send_match_log`.
2. Шаг 0: `web_logger/pg_bridge.py` + старт из `asgi.py`.
3. Шаг 1: добавить `send_match_log` в `web_logger/weblogger.py` + экспорт.
4. Шаг 2.1: `match_start` / `match_result` в `tmdb_movie_sync_service.py` + тест.
5. Шаг 2.2: `tmdb_search` в `tmdb_movie_matching_service.py` + тест.
6. Шаг 2.3: события в `tmdb_smart_search_service.py` + тест.
7. Шаг 2.4-2.5: события в `tmdb_match_resolver.py` и `tmdb_groq_matching_service.py` + тест.
8. Шаг 3: создать страницу `/match-log` + WebSocket-подключение.
9. Шаг 4: добавить пункт в шапку сайта.
10. Шаг 5: проверить consumer (payload уже пересылается как есть — изменений не требуется).

> [!IMPORTANT]
> Каждый шаг — отдельная задача. Пользователь тестирует перед переходом к следующему.
