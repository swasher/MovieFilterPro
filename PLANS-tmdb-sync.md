# План: Массовая синхронизация всех фильмов Vault с TMDB (страница "TMDB Sync Queue")

## 0) Цель

Сделать отдельную страницу **"TMDB Sync Queue"**, через которую можно запустить автоматическую
поочерёдную синхронизацию **всех** фильмов Vault (пришедших из Kinorium CSV), не нажимая кнопку
`Fetch` на каждом фильме вручную.

Пользователь должен на странице видеть:

- кнопку **«Добавить все»** — добавляет все не синхронизированные фильмы в очередь;
- кнопки **Start / Stop** — запускают/останавливают обработку очереди
  (Stop не прерывает текущую синхронизацию, а лишь останавливает все последующие);
- кнопку **Remove all** — очищает очередь и ставит флаг Stop;
- **«лог действий»** — таблицу на всю ширину браузерного окна, где для каждого элемента очереди видно:
  - в каком он состоянии (ждёт / синхронизируется / синхронизирован / требует подтверждения / ошибка);
  - какие данные были **до** (из Kinorium): `title`, `original_title`, `year`;
  - какие данные получил **после** (из TMDB): `title`, `original_title`, `year`;
  - в таблице могут быть action-кнопки (если понадобятся);
- темп: **1 фильм в X секунд**, где X настраивается (чтобы не упереться в лимиты TMDB API);
- таблица **температивно обновляется** — после каждого обновлённого фильма UI реактивно перерисовывается.

Вход на страницу — в главном NavBar, в выпадающем меню по клику на username, пункт **"TMDB Sync Queue"**.

---

## 1) Быстрый аудит текущего состояния

### 1.1. Уже реализовано (рабочая база)
- `vault/services/tmdb_movie_sync_service.py` — `TMDBMovieSyncService.sync_movie(movie, force_rematch, selected_candidate)`.
  Синхронизирует поля, жанры, страны, состав, постеры, сезоны, ставит `tmdb_id`, `tmdb_media_type`,
  `tmdb_last_synced_at`, `source=TMDB`.
- `vault/services/tmdb_movie_matching_service.py` — матчинг; возвращает статусы:
  `auto_match` / `needs_confirmation` / `needs_user_choice` / `not_found`.
- `TMDBMovieSyncService.sync_movie` возвращает `TMDBSyncResult(status: ok|needs_confirmation|needs_user_choice|error, ...)`.
  Важно: при `needs_confirmation`/`needs_user_choice` данные фильма НЕ меняются, `tmdb_id` НЕ ставится.
- Одиночная кнопка **Fetch** уже реализована в новом фронте:
  - `POST /api/vault/movies/{slug}/fetch-tmdb` (`vault/api.py:721`)
  - `POST /api/vault/movies/{slug}/fetch-tmdb-confirm` (явный выбор кандидата)
- HUEY-инфраструктура уже есть:
  - `movie_filter_pro/huey.py` — `SqliteHuey` + запись результата;
  - `vault/tasks.py` — задачи (`process_kinozal_download_import`, `process_kinozal_hide_action`);
  - запуск воркера: `make huey` (`huey_consumer movie_filter_pro.huey.HUEY -k thread -w 2 -S`)
    и `supervisord.conf`.

### 1.2. Что важно знать о данных
- Фильмы после `import_kinorium_csv` имеют `source=KINORIUM`, `tmdb_id=NULL`, `tmdb_last_synced_at=NULL`.
- За один успешный sync `tmdb_id` и `tmdb_last_synced_at` ставятся вместе (под `transaction.atomic`);
  при ошибке/ambiguous данные НЕ трогаются (`tmdb_id` остаётся NULL).
- => **«не синхронизирован»** формально = `Movie.tmdb_id IS NULL` (и `source=KINORIUM`).

### 1.3. Ограничения HUEY, которые надо учесть
- `crontab()` поддерживает только **минутную** гранулярность (нет секунд).
- Есть `HUEY.schedule(func, args, kwargs, delay=seconds)` — отложенный запуск задачи на `eta=now+X`.
- Есть `HUEY.pending()`, `HUEY.scheduled()`, `HUEY.result(task_id)` для introspection, но для UI
  надёжнее ориентироваться на собственное состояние в БД (см. раздел 3).
- Воркер может работать с `-w 2` → нужна защита от двух одновременных «тиков» (`HUEY.lock_task`).

---

## 2) UX и целевой flow

### 2.1. Страница (`/tmdb-sync`)
Полновесная страница без Vault-сайдбара (как `/scan`, `/kinozal`).

Верхняя панель управления:
- `Добавить все` — создаёт записи очереди для всех несинхронизированных фильмов (см. 5.1), обработку НЕ запускает.
- `Start` — включает флаг «обработка включена» и ставит в HUEY первый «тик» (запуск обработки).
- `Stop` — снимает флаг; текущий фильм дорабатывается, следующие не запускаются.
- `Remove all` — вычищает все записи очереди **и ставит флаг Stop**.
- Селектор/инпут `Темп: 1 фильм в N сек` (значение по умолчанию 60, сохраняется в БД).
- Счётчики: сколько в очереди / сделано (секунды справа) / ошибок / неуверенных.

Ниже — **«лог действий»**: таблица во всю ширину браузерного окна.

| Статус | «До» (Kinorium) | «После» (TMDB) | Результат | Action | Время |
|--------|-----------------|----------------|-----------|--------|-------|
| pending | title (orig) 1996 | — | ждёт очереди | — | 12:10:00 |
| in_progress | … | … | синхронизируется… | — | 12:10:05 |
| synced | … | title (orig) 2023 | ok: tmdb_id=… | [Открыть] | 12:10:12 |
| confirm | … | кандидаты | нужен ручной выбор | [Выбрать] | 12:10:20 |
| not_found | … | — | не найдено | — | 12:10:25 |
| error | … | — | ошибка + причина | — | 12:10:30 |

Для `confirm`/`needs_user_choice` — ссылка на страницу фильма, где уже есть модалка подтверждения кандидатов.

### 2.2. NavBar
В `front/src/lib/components/SiteShell.svelte`, в `DropdownMenu.Group` (там где «Django Admin» и «События связок»),
добавить пункт **«TMDB Sync Queue»** со ссылкой на `/tmdb-sync` (+ иконка), например `RefreshCw` из lucide-svelte.

---

## 3) Ключевое архитектурное решение: очередь в БД + «тик-координатор» в HUEY

### 3.1. Проблема в исходной постановке
Формально «фильмы попадают в очередь HUEY», но HUEY не умеет:
- соблюдать темп «1 фильм в X секунд» для уже поставленных в очередь задач;
- показывать прогресс/детали («до/после», «кто в очереди, что уже сделано») — для этого всё равно
  пришлось бы дублировать состояние во внешнем хранилище;
- атомарно делать «Remove all» (отзыв множества задач).

Если бы мы на каждый фильм заводили `HUEY.task` с `delay = i * X`, то:
- нельзя корректно сделать Stop (отзыв пачки задач через `huey.revoke`);
- не видно «что уже сделано» без отдельной таблицы;
- порядок и темп ломаются при перезапусках.

### 3.2. Принятое решение (гибрид)
- **Очередь (список фильмов и результатов) живёт в БД** — модель `TMDBSyncQueueItem`.
  Это единственный источник правды: для UI, для персистентности, для восстановления после рестарта.
- **Исполнитель — один HUEY-«тик»** (`tmdb_sync_tick`), который при вызове:
  1. проверяет флаг «обработка включена» (в `UserPreferences`);
  2. берёт следующий `pending`-элемент из БД, помечает `in_progress`;
  3. вызывает `TMDBMovieSyncService.sync_movie(movie_id)`;
  4. записывает результат (статус + данные «после»);
  5. если обработка ещё включена и есть ещё pending → сам перепланирует себя через
     `HUEY.schedule(tmdb_sync_tick, delay=delay_seconds)`;

  Результат: темп «1 фильм в X сек» достигается само-перепланированием тика, Queue-UI показывает
  список записей, Start/Stop/Remove-all тривиальны (один флажок + чистка записей), рестарт воркера
  догоняется watchdog-задачей.

### 3.3. Почему не чистый «cron» как в HUEY docs (вопрос #1)
Пример в доке `huey.contrib.djhuey` — «tasks that execute queries» — показывает `@db_periodic_task(crontab(...))`,
периодическую задачу, которая сама выбирает строки и обрабатывает их. Как это соотносится с нами:

- **Что можно взять**: саму идею периодического «слейв-задания» без self-chaining — пригодится как
  страховочный **watchdog** (раздел 6): `@HUEY.periodic_task(crontab(minute='*/1'))` будет проверять
  «включено ли + есть ли pending», и подталкивать тик. Это работает с нашим `SqliteHuey` даже без
  django-extension — обычная `periodic_task` доступна и на `HUEY` из `movie_filter_pro/huey.py`.
- **Почему этого недостаточно как главного механизма**: у `crontab` **минутная гранулярность**.
  Поддерживать «1 фильм в X секунд» (например 10–30 секунд) при произвольном X — нельзя: либо «все разом
  раз в N минут», либо грубый батч `ceil(60/X)` штук всплесками (плохо для лимитов API).
- **Вывод**: основной темп держим на саморасписание HUEY-тика (`delay=X`), а крон-аналог из доков
  используем только как «watchdog» восстановления после рестарта воркера. Подключение django-extension
  (`settings.HUEY`, `manage.py run_huey`. `db_task`) не делаем — это изменение работающей инфраструктуры
  без выигрыша.

---

## 4) Изменения в моделях (минимальные, но необходимые)

### 4.1. Новая модель `vault/models.py` — `TMDBSyncQueueItem`

```python
class TMDBSyncQueueItem(models.Model):
    class State(models.TextChoices):
        PENDING = 'pending', 'Ждёт очереди'
        IN_PROGRESS = 'in_progress', 'Синхронизируется'
        SYNCED = 'synced', 'Синхронизирован'
        CONFIRM = 'confirm', 'Нужен ручной выбор'
        NOT_FOUND = 'not_found', 'Не найден'
        ERROR = 'error', 'Ошибка'

    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='tmdb_sync_items')

    # snapshot данных «До» (из Kinorium) на момент постановки в очередь
    snapshot_title = models.CharField(max_length=255)
    snapshot_original_title = models.CharField(max_length=255, blank=True, default='')
    snapshot_year = models.PositiveSmallIntegerField(null=True, blank=True)
    snapshot_movie_type = models.CharField(max_length=20)
    snapshot_imdb_id = models.CharField(max_length=15, blank=True, default='')
    snapshot_kinopoisk_id = models.PositiveIntegerField(null=True, blank=True)

    state = models.CharField(max_length=20, choices=State, default=State.PENDING, db_index=True)
    queued_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)

    # результат «Доcле»
    result_status = models.CharField(max_length=30, blank=True, default='')  # ok/needs_confirmation/needs_user_choice/not_found/error
    result_title = models.CharField(max_length=255, blank=True, default='')
    result_original_title = models.CharField(max_length=255, blank=True, default='')
    result_year = models.PositiveSmallIntegerField(null=True, blank=True)
    result_tmdb_id = models.PositiveIntegerField(null=True, blank=True)
    result_media_type = models.CharField(max_length=10, blank=True, default='')  # movie/tv
    result_message = models.TextField(blank=True, default='')
    error_trace = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['queued_at', 'id']
```

Примечания:
- снапшот «До» обязателен: после успешного sync `movie.title/original_title/year` уже заполнены данными TMDB,
  поэтому «до» без снапшота утеряется.
- `state=confirm` объединяет `needs_confirmation` и `needs_user_choice` (для UI достаточно; детали в `result_message`).

### 4.2. Поля в `moviefilter.models.UserPreferences` (singleton pk=1)
- `tmdb_sync_enabled = models.BooleanField(«Обработка очереди TMDB включена», default=False)`
- `tmdb_sync_delay_seconds = models.PositiveSmallIntegerField(«Секунд на фильм при массовой синхронизации», default=60)`

«Влючен или нет» хранится в БД-синглоне ✅ доступно и web-запросу, и воркеру; при рестарте воркера
состояние Start/Stop не теряется. `UserPreferences.get()` — существующий доступ.

### 4.3. Миграции
Две новые миграции: `vault` (модель `TMDBSyncQueueItem`) и `moviefilter` (2 новых поля).
`uv run python manage.py makemigrations vault moviefilter`, затем `uv run python manage.py migrate`.

---

## 5) Backend: сервис очереди `vault/services/tmdb_sync_queue_service.py`

Новый сервис-слой (по правилу AGENTS — логику держим в services, не во views):

```
# ------------------------------------ #
#          APPLICATION LAYER          #
# ------------------------------------ #
```

### 5.1. `enqueue_unsynced() -> dict` (кнопка «Добавить все»)
1. Выборка целей (несинхронизированные фильмы):
   ```python
   qs = Movie.objects.filter(source=Movie.Source.KINORIUM, tmdb_id__isnull=True)
   ```
   *Обратите внимание: вопрос №6 решён — берём только `source=KINORIUM` + `tmdb_id IS NULL`.*
2. Исключить фильмы, у которых уже есть запись в очереди с любым состоянием (**вопрос №5 решён**):
   не добавляем заново снятые или уже обработанные записи (error/not_found/confirm остаются в таблице как
   историмость, повторно не пытаемся).
3. Для каждого фильма без записи создать `TMDBSyncQueueItem` с снапшотом «До».
4. Вернуть `{added: N, total: M}` (сколько добавлено, сколько в очереди всего).

Примечание: если фильм был в очереди, но его запись удалил «Remove all», при следующем «Добавить все»
он снова попадёт в очередь (таблица пуста → новых двойников нет).

### 5.2. `start() -> None` (кнопка Start)
1. `prefs.tmdb_sync_enabled = True`, сохранить.
2. Запланировать немедленный тик: `HUEY.schedule(tmdb_sync_tick, delay=1)` (подхватит первый pending).

### 5.3. `stop() -> None` (кнопка Stop)
1. `prefs.tmdb_sync_enabled = False` (текущий тик доделывает фильм, следующие не перепланируются).

### 5.4. `remove_all() -> int` (кнопка Remove all)
1. Удалить все `TMDBSyncQueueItem` (одну транзакцию delete).
2. **Выставить `prefs.tmdb_sync_enabled = False`** (вопрос №3 решён — Remove all также делает Stop).
   Текущий тик дорабатывает текущий фильм и завершается (pending нет).

### 5.5. `set_delay(seconds)` / `get_state()`
- `set_delay`: валидация (например 1..3600), запись в `UserPreferences`.
- `get_state()`: `{enabled, delay_seconds, pended, in_progress, synced, confirm, not_found, error}`.

### 5.6. `process_one()` (исполнитель тика)
1. `if not prefs.tmdb_sync_enabled: return` (стоп — не запускаем новую итерацию).
2. Взять следующий `state=PENDING` по `queued_at` (порядок добавления).
3. Защита от «двойного тика» с `-w 2`: если уже есть `state=IN_PROGRESS` элемент — выйти
   (или `HUEY.lock_task('vault_tmdb_sync_tick')` как дополнительная страховка).
4. `started_at=now`, `state=IN_PROGRESS`, `save`.
5. Вызов:
   ```python
   movie = Movie.objects.get(pk=item.movie_id)
   result = TMDBMovieSyncService.sync_movie(movie)
   ```
6. Результат:
   - `ok` → `state=SYNCED`, `result_title/original_title/year` — из `movie` (это обновлённые данные TMDB),
     плюс `result_tmdb_id`, `result_media_type`;
   - `needs_confirmation`/`needs_user_choice` → `state=CONFIRM`, `result_status=...`, `result_message=result.message`,
     список кандидатов положить в `result_message` (или отдельное JSON-поле);
   - `error`/исключение → `state=ERROR`, `result_message`, `error_trace=traceback`.
   `finished_at=now`.
7. Перепланирование:
   ```python
   if prefs.tmdb_sync_enabled and TMDBSyncQueueItem.objects.filter(state=PENDING).exists():
       HUEY.schedule(tmdb_sync_tick, delay=prefs.tmdb_sync_delay_seconds)
   ```

### 5.7. Watchdog (периодическая подстраховка, в вопросы #1)
`@HUEY.periodic_task(crontab(minute='*/1'))`:
- если `prefs.tmdb_sync_enabled` и есть pending-элементы и «тик» сейчас не выполняет active item
  → `HUEY.schedule(tmdb_sync_tick, delay=1)`.
- Назначение: автоматически перезапустить цепочку после рестарта воркера; не обязателен, рекомендован.

---

## 6) Backend: HUEY-задачи (`vault/tasks.py`)

```python
@HUEY.task()
def tmdb_sync_tick():
    return TMDBSyncQueueService.process_one()

@HUEY.periodic_task(crontab(minute='*/1'))
def tmdb_sync_watchdog():
    TMDBSyncQueueService.watchdog()
```

Оба — в том же `vault/tasks.py`, который уже импортируется в `movie_filter_pro/huey.py`
(изменений в запуск воркера не требуется).

---

## 7) Backend: API-эндпоинты (`vault/api.py`, через `_require_api_user`)

| Метод | Путь | Назначение |
|---|---|---|
| GET  | `/api/vault/tmdb-sync/state` | `{enabled, delay_seconds, counters}` |
| POST | `/api/vault/tmdb-sync/queue` | «Добавить все» → `{added, total}` |
| DELETE | `/api/vault/tmdb-sync/queue` | Remove all → `{deleted}` |
| POST | `/api/vault/tmdb-sync/start` | Start |
| POST | `/api/vault/tmdb-sync/stop` | Stop |
| PATCH | `/api/vault/tmdb-sync/state` | установка `delay_seconds` |
| GET  | `/api/vault/tmdb-sync/items?offset=&limit=&state=` | список записей (сортировка по `queued_at`) |

Schemas (django-ninja):

```python
class TMDBSyncQueueStateOut(Schema):
    enabled: bool
    delay_seconds: int
    counters: dict[str, int]   # pending, in_progress, synced, confirm, not_found, error
    total_unsynced: int        # сколько в базе вообще несинхронизированных (source=KINORIUM, tmdb_id IS NULL)

class TMDBSyncQueueItemOut(Schema):
    id: int
    movie_id: int
    movie_slug: str
    movie_title: str                # актуальный title (для быстрой ссылки)
    snapshot_title: str
    snapshot_original_title: str
    snapshot_year: int | None
    state: str
    queued_at: str
    started_at: str | None
    finished_at: str | None
    result_status: str
    result_title: str
    result_original_title: str
    result_year: int | None
    result_tmdb_id: int | None
    result_media_type: str
    result_message: str
    retry_count: int
```

`total_unsynced` нужен, чтобы на странице сразу было видно: «очередь содержит X из Y несинхронизированных».

---

## 8) Frontend: Svelte-страница `/tmdb-sync`

### 8.1. Route-файлы
- `front/src/routes/tmdb-sync/+page.ts` — `load`: fetch `GET /api/vault/tmdb-sync/state` + `GET /.../items`.
- `front/src/routes/tmdb-sync/+page.svelte` — UI.

### 8.2. UI (Svelte 5, runes only, shadcn-svelte)
Верхняя панель управления (Card):
- `Добавить все` — `POST /rm-sync/queue`, тост, обновить state.
- `Start` (disabled при `enabled`) / `Stop` (disabled при `!enabled`).
- `Remove all` — `DELETE /rm-sync/queue` (с confirm-dialog), тост.
- `Темп: 1 фильм в N сек` — числовой Input, save on blur/Тиктер: `PATCH /state`.
- Статус-бейдж: «Идёт обработка…» (пульс) / «Остановлено» / «Очередь пуста».
- Счётчик: `pending N · synced M · confirm K · error E · not_found F`.

**«Лог действий» — таблица на всю ширину окна (primary)**:
- Table со `w-full`, колонки (см. 2.1): Статус | «До» | «После» | Результат | Action | Время.
- `До`/`После` — компактно: `title`, `original_title`, `year`;
- `confirm` — ссылка «Выбрать» → `/movies/<slug>` (там уже есть модалка кандидатов);
- `synced` — зелёный бейдж, `error` — red, `not_found` — warning;
- `in_progress` — spinner.
- Action-колонка: ссылка «Открыть» (movie slug) и резервно место для будущих кнопок.

**Реактивность/динамическое обновление (заявленное требование):**
- после любого действия (Добавить/Start/Stop/Remove) сразу `fetch` заново;
- таймер `setInterval(() => refresh(), 3000)` внутри `$effect` (SPA, `ssr=false`);
- при открытой вкладке и `document.hidden` — пауза таймера (визible API);
- новый ответ перезаписывает `let items = $state([...])`, Svelte перерисовывает таблицу заново —
  когда воркер закончит фильм, следующий poll покажет новый статус мгновенно (интервал ≤ 3 с);
- при `enabled` интервал можно уменьшить до ~2 с, чтобы «каждый обновлённый фильм» появлялся сразу.

Правила AGENTS: только runes; UI — только shadcn-svelte (Button, Card, Badge, Input, Table, DropdownMenu и т.п.).
Недостающие компоненты (`Table`) — через CLI shadcn-svelte, без самодельных замен.

### 8.3. NavBar
`SiteShell.svelte` → добавить «TMDB Sync Queue» в dropdown.username (раздел 2.2).

---

## 9) Логи и отладка
- Используем существующий логгер `vault.tmdb_sync` (`logs/debug.log`, `print` в воркере).
- При массовой обработке тик логирует: `QUEUE_START item=<id> movie=<id> title="..."`, `QUEUE_DONE item=? status`.
- В `TMDBSyncQueueItem.result_message` / `error_trace` — компактное человекочитаемое описание, которое и
  показывается в таблице (это и есть «подробный лог очереди»).

---

## 10) Тестирование (минимум)

Сервис `tmdb_sync_queue_service` (mock `sync_movie` / TMDB client):
1. `enqueue_unsynced` добавляет всех `source=KINORIUM` + `tmdb_id IS NULL`, не создаёт дубли
   и не трогает фильмы, у которых уже есть запись в очереди (текущая history не перезаписывается).
2. `process_one` начал сторона при `enabled=False`.
3. `process_one` переводит `pending -> in_progress -> synced`, заполняет `result_*`.
4. `process_one` при `needs_user_choice` ставит `state=CONFIRM` и сохраняет сообщение.
5. Исключение внутри `sync_movie` → `state=ERROR` + `error_trace`.
6. Перепланирование: есть ещё pending + enabled → тик планируется заново с `delay`.
7. `remove_all` удаляет записи и ставит `enabled=False`.
8. Start/Stop меняют флаг в `UserPreferences.get()`.

Фронт: ручная проверка «Добавить все → Start → следить в таблице → Stop → Remove all».

---

## 11) Вопросы и решения (по результатам обсуждения)

| # | Вопрос | Решение |
|---|---|---|
| 1 | Хроника HUEY docs (django-extension, `db_periodic_task`+`crontab`) | Применим как **watchdog**; минуты-гранулярность crontab не даёт «X секунд»; основной темп на само-расписание HUEY-тика. django-extension не подключаем. |
| 2 | Где хранить флаг Start/Stop и темп | `UserPreferences.tmdb_sync_enabled` + `tmdb_sync_delay_seconds` (синглтон). Принято. |
| 3 | Что делает Remove all | Удаляет все записи очереди **и ставит флаг Stop**. Принято. |
| 4 | «Добавить все» и «Вытащить все фильмы» | Это одна и та же кнопка. Принято (1 CTA «Добавить все»). |
| 5 | Ошибка/неуверенный матч — повторная попытка? | Повторно НЕ пытаемся; ошибки остаются в таблице явной записью. Логику их дальнейшей судьбы придумаем позже. Принято. |
| 6 | Целевая выборка | `source=KINORIUM` и `tmdb_id IS NULL`. Принято. |
| 7 | `UserPreferences.get()` | Работает в текущей схеме. Принято. |
| 8 | Живое обновление таблицы | Polling через `setInterval` (интервал опционально ~1–3 с) + перезапись реактивного состояния; таблица перерисовывается после каждого фильма. Принято. |

---

## 12) Критерии готовности (Definition of Done)

1. `GET /api/vault/tmdb-sync/state` и `/items` работают и показывают актуальные счётчики и очередь.
2. «Добавить все» создаёт очередь для всех `source=KINORIUM` + `tmdb_id IS NULL`, не делает дубли.
3. Start включает флаг и запускает тик; Stop останавливает последующие, текущий фильм не прерывает.
4. Темп: между обработкой двух фильмов проходит не меньше N секунд (N = настройка).
5. Таблица «До/После» показывает (title, original_title, year) для каждого элемента и статус-бейдж.
6. Для `confirm`/`needs_*` есть ссылка/действие на страницу фильма с модалкой выбора.
7. `Remove all` удаляет все записи и ставит Stop.
8. Пункт «TMDB Sync Queue» в NavBar (dropdown username) ведёт на страницу.
9. Таблица персистируется (история видна после перезагрузки страницы) и обновляется динамически.
10. `uv run python manage.py check` и тесты раздела 10 проходят.