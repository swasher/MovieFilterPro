# План: зеркальный TMDB-список «Просмотрено»

## 1. Контекст

В `vault` есть системный статус `UserMovie.watch_status=WATCHED` (`vault/models.py:493`) + `rating 1..10`. Он существует независимо от оценки: фильм может быть `WATCHED` без `rating`.

В TMDB нет статуса «просмотрено». Есть только:
* `watchlist` -> `PLAN`
* `favorite` -> `is_favorite`
* `rating` -> `rate()/delete_rating()`

Маппинг сейчас `docs/WRITEBACK_IMPLEMENTATION.md:72` + `vault/services/tmdb_writeback_service.py:530`:
* `WATCHED` -> `remove_from_watchlist()` и всё. Без `rating` следа на TMDB не остаётся — lossy sync.

`SKIP` уже решён зеркальным скрытым списком: `UserPreferences.tmdb_skip_list_id` (`moviefilter/models.py:195`) + `TmdbWritebackService.sync_skip_list()` / `_ensure_skip_list_tmdb_id()`.

Задача — сделать то же для `WATCHED`.

## 2. Состояние БД (важно)

* Тестовая БД, которую видит AI — игнорировать.
* Прод-БД: фильмы **ещё не синхронизированы** (`Movie.tmdb_id IS NULL`, `source=KINORIUM`), очередь `TMDBSyncQueueItem` пуста и ждёт запуска `enqueue_unsynced` -> `process_one`.

**Следствие:** отдельного backfill/management command для «дозаполнения» списка `Просмотрено` не нужно.

Если логика написана правильно, всё заполнится само по существующему конвейеру:

```
import_kinorium_csv -> Movie без tmdb_id (writeback guard skip)
        |
enqueue_unsynced -> TMDBSyncQueueService.process_one() -> TMDBMovieSyncService.sync_movie() -> movie.tmdb_id появился
        |
TMDBSyncQueueService.process_one():314 после SYNCED -> TmdbWritebackDispatch.schedule_user_movie_writeback(user_movie_id, changed_fields=None)
        |
TmdbWritebackService.sync_user_movie_to_tmdb() -> sync_watched_list() -> list_add_items
```

И далее любые ручные `set_status`/`rate_movie`/`remove_rating` триггерят тот же путь через `vault/signals.py:34` `post_save`.

Т.е. прод заполнится лениво, по мере прохода очереди. Специальный код пересинхронизации не пишем.

## 3. Решение

Скрытый системный зеркальный список `Просмотрено`, по образу `Не интересует`.

* Локально: истина — `UserMovie.watch_status == WATCHED`. Никакого `UserList`.
* На TMDB: отдельный V4 List с именем `Просмотрено` (`WATCHED_LABEL`), `id` хранится в `UserPreferences.tmdb_watched_list_id`.
* Идемпотентно: `WATCHED` -> `list_add_items`, иначе `list_remove_items`.

Видимый `UserList` не делаем (требование).

## 4. Проектирование

### 4.1 Константы `vault/constants.py:16`

```python
WATCHED_LIST_NAME = WATCHED_LABEL  # "Просмотрено"
```

`SKIP_LIST_NAME` уже есть. Добавить рядом.

### 4.2 Модель `moviefilter/models.py:134` `UserPreferences`

```python
tmdb_watched_list_id = PositiveIntegerField(null=True, blank=True, help_text='ID TMDB-листа "Просмотрено"')
```

Миграция `moviefilter/migrations/`. Singleton `pk=1`.

### 4.3 Сервис `vault/services/tmdb_writeback_service.py`

Прямое дублирование логики `SKIP` без общего helper (решение YAGNI, §8):

* `_ensure_watched_list_tmdb_id(prefs=None) -> int` — копия `_ensure_skip_list_tmdb_id():628` с заменой `SKIP_LIST_NAME` на `WATCHED_LIST_NAME`, `tmdb_skip_list_id` на `tmdb_watched_list_id`, тот же fast-path (кэш без `list_get_list`), slow-path с `account_get_lists` поиск по имени + `list_create_list`, `threading.Lock` + `select_for_update`.
* `sync_watched_list(user_movie, prefs=None) -> WritebackResult | None` — копия `sync_skip_list():705` с условием `watch_status == WATCHED` -> `add`, else `remove`. 404 -> сброс `tmdb_watched_list_id=None` -> пересоздание и один ретрай.
* В `sync_user_movie_to_tmdb():303` добавить ветку аналогично `sync_skip_list`:
  ```python
  if _should_run("watch_status"):
      r = cls.sync_watched_list(user_movie, prefs=prefs)
  ```
  Список — производное от `watch_status`, поэтому биндим к `watch_status` (как skip). Отдельного `lists` не нужно.
* В `sync_user_movie_deleted():499` добавить cleanup `list_remove_items` для `tmdb_watched_list_id` (как сейчас для skip).

Ошибки классифицируются так же: `429` -> `TMDBWritebackQueueItem` pending с backoff, `401` -> `ERROR` без ретрая.

Общий `_ensure_mirror_list` / `_sync_mirror_list` не выносим: всего 2 зеркала, 4 системных списка из которых 2 маппятся напрямую на TMDB. Абстракция не окупится, оставит дублирование ~120 строк осознанно.

### 4.4 Сигналы `vault/signals.py:168`

Добавить guard как для skip:

```python
@receiver(post_save, sender=UserList)
def on_userlist_saved(...):
    if instance.name in (SKIP_LIST_NAME, WATCHED_LIST_NAME):
        return
```

Иначе пользовательский `UserList` с именем `Просмотрено` будет пытаться создать TMDB-лист и конфликтовать с зеркалом.

`UserMovie` сигналы трогать не нужно — `changed_fields` уже содержит `watch_status`, через него сработает `sync_watched_list`.

### 4.5 Очередь `vault/models.py:645` `TMDBWritebackQueueItem`

Одна запись на `movie_id` уже покрывает все sub-sync. Дополнительных полей не нужно. `tmdb_writeback_retry_tick` `vault/tasks.py:182` ретраит `sync_user_movie_to_tmdb(full)` — подхватит и watched.

### 4.6 Диспетчер `vault/services/tmdb_writeback_dispatch.py:18`

Нового метода не нужно, всё через `schedule_user_movie_writeback`.

## 5. Поток данных

```
set_status(watched) / rate_movie() / remove_rating() (оставляет WATCHED)
  -> UserMovie.save() -> pre_save snapshot -> post_save -> transaction.on_commit -> schedule_user_movie_writeback
  -> HUEY tmdb_writeback_user_movie (delay 2s, dedup) -> sync_user_movie_to_tmdb
     -> sync_watch_status (remove_from_watchlist)
     -> sync_rating (if changed)
     -> sync_skip_list (remove, т.к. не SKIP)
     -> sync_watched_list (add)

unset_status(watched) / set_status(will_watch/wont_watch)
  -> sync_watched_list (remove)

UserMovie.delete()
  -> sync_user_movie_deleted -> remove_from_watched_list + remove_from_skip_list + ...
```

## 6. Edge cases

* `Movie.tmdb_id IS NULL` -> guard `_should_writeback` skip, ничего не делаем.
* `watch_status=None` + `rating` остался (после `unset_status(watched)` без `remove_rating`) — фильм останется `rated` на TMDB, но уйдёт из списка `Просмотрено`. Это консистентно с «список = watch_status», не «список = rating exists». Так и задумано.
* `WATCHED -> SKIP` -> `remove` из watched + `add` в skip = 2 лист-вызова в одной транзакции writeback.
* Фильм уже в списке на TMDB -> `list_add_items` идемпотентен (TMDB не дублирует), считаем успехом.
* Список удалён на TMDB вручную -> 404 -> сброс `tmdb_watched_list_id` -> пересоздание + один ретрай (как у skip).
* `writeback disabled` / нет токена -> skip с `reason`, без очереди.

## 7. Проверка

1. `uv run python manage.py check && makemigrations && migrate`
2. Ручной тест: фильм с `tmdb_id` -> `toggle_status watched` -> через 2с в `logs/debug.log` `writeback watched_list add`, на TMDB в списке `Просмотрено` появился.
3. `remove_rating` оставляет в списке, `unset_status watched` удаляет.
4. `WATCHED -> SKIP` -> из `Просмотрено` удалён, в `Не интересует` добавлен.
5. Удаление `UserMovie` -> из обоих зеркальных списков удалён.
6. Массовый прогон: `enqueue_unsynced` на проде -> после `process_one` каждый `WATCHED` оказывается в TMDB списке без доп. команд.

## 8. Что не делаем

* Backfill management command — не нужен из-за состояния прод-БД (см. §2).
* Видимый `UserList` — отказ.
* Отдельный `tmdb_lists_init` для watched — не нужно, ленивый `_ensure` достаточно.
* Изменение `TmdbRateLimiter` — остаётся 0.5с, доп. вызов укладывается в лимит.
* Общий mirror helper `_ensure_mirror_list` / `_sync_mirror_list` — не делаем. Осознанное дублирование `SKIP`/`WATCHED` (~120 строк), YAGNI: всего 2 зеркала из 4 системных списков.

## 9. Файлы для правок

* `vault/constants.py` — `WATCHED_LIST_NAME`
* `moviefilter/models.py` + миграция — `tmdb_watched_list_id`
* `vault/services/tmdb_writeback_service.py` — `sync_watched_list`, `_ensure_watched_list_tmdb_id`, интеграция в `sync_user_movie_to_tmdb` и `sync_user_movie_deleted` (копия skip-логики, без абстракции)
* `vault/signals.py` — guard для `WATCHED_LIST_NAME`
* `docs/WRITEBACK_IMPLEMENTATION.md` — таблица маппинга + §6.4
