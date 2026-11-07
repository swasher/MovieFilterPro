Принял: **LRU + жёсткий лимит размера + TTL, единый бюджет на весь `CACHE_ROOT`, лимит 2 ГБ.**

## Итоговый план

### 1. Настройки

Добавить в `settings.py` (значения из `.env`, с дефолтами):

```python
IMAGE_CACHE_MAX_BYTES = 2048 * 1024 * 1024       # 2 ГБ
IMAGE_CACHE_MAX_AGE_DAYS = 90
IMAGE_CACHE_TARGET_RATIO = 0.70                  # чистить до 1.4 ГБ
IMAGE_CACHE_PROTECT_RECENT_SECONDS = 600         # не трогать то, что смотрели 10 минут
IMAGE_CACHE_MIN_FREE_BYTES = 512 * 1024 * 1024   # аварийный порог свободного места
```

Соответствующие env-переменные: `IMAGE_CACHE_MAX_MB`, `IMAGE_CACHE_MAX_AGE_DAYS`, `IMAGE_CACHE_MIN_FREE_MB`.

### 2. Учёт последнего обращения

Для LRU нужен «last access». `atime` в Docker/`relatime` ненадёжен, поэтому:

- в `vault/services/image_cache.py` при выдаче готового файла вызывать `touch_cache_file(path)`;
- в `moviefilter/api.py::movie_poster` — тоже при отдаче Kinozal-постера;
- `touch_cache_file` обновляет `mtime` через `os.utime`, но **не чаще раза в час** на файл.

Это даёт LRU без отдельной БД и почти без накладных расходов.

### 3. Сервис очистки

Новый модуль `core/image_cache_maintenance.py` — потому что бюджет общий для Vault и Kinozal.

Алгоритм:

1. Просканировать `CACHE_ROOT` без следования symlink/junction.
2. Классифицировать файлы:
    - изображения — по расширениям `.jpg/.jpeg/.png/.webp/.gif/.avif`;
    - `.missing` / `.failed` — маркеры;
    - `.tmp` — временные файлы;
    - остальное — не трогать.
3. Удалить изображения старше `IMAGE_CACHE_MAX_AGE_DAYS`.
4. Посчитать суммарный размер изображений.
5. Если размер > 2 ГБ — удалять самые старые по `mtime`, пока не дойдёт до 70% (1.4 ГБ).
6. Файлы, изменённые за последние 10 минут, при size-очистке пропускать.
7. Удалить мусор:
    - `.tmp` старше часа;
    - просроченные `.missing` / `.failed`;
    - маркеры, у которых уже есть основной файл;
    - пустые каталоги.
8. Вернуть статистику: просканировано, удалено по TTL, удалено по размеру, итоговый объём.

### 4. Запуск

- **Huey periodic task** раз в 15 минут в новом `core/tasks.py`:
    - `@HUEY.periodic_task(crontab(minute="*/15"))`
    - `@HUEY.lock_task("image_cache_cleanup")`, чтобы задачи не накладывались.
- Подключить `core.tasks` в `movie_filter_pro/huey.py`.
- **Management command** для ручного запуска и проверки:

```bash
uv run python manage.py clean_image_cache --dry-run
uv run python manage.py clean_image_cache --max-size-mb 2048 --max-age-days 90
```

Одна и та же сервисная функция используется и таской, и командой.

### 5. Защита от переполнения диска

Перед скачиванием в `ImageCache._download` проверять свободное место:

```python
free = shutil.disk_usage(cache_root).free
if free < IMAGE_CACHE_MIN_FREE_BYTES:
    # не качаем, показываем заглушку
```

Плюс periodic cleanup как основной механизм. Это страховка на случай, если за короткое время скачается очень много изображений.

### 6. Что не меняется

- `MEDIA_ROOT` не затрагивается вообще.
- URL изображений остаются стабильными: удалённый файл просто скачается заново.
- `ImageService` и модели по-прежнему ничего не знают про eviction.
- `original`-изображения участвуют в общем бюджете. Если 2 ГБ начнёт не хватать, позже можно добавить отдельную квоту или короткий TTL для `original` — но это уже тонкая настройка, не обязательная.

### 7. Тесты

- TTL-удаление.
- Порядок LRU-вытеснения.
- High/low watermark: 2 ГБ → очистка до 1.4 ГБ.
- Защита свежих файлов.
- Очистка `.tmp`, `.missing`, `.failed`, пустых каталогов.
- Проверка, что `MEDIA_ROOT` не изменяется.
- `touch_cache_file` не обновляет `mtime` чаще заданного интервала.
- `clean_image_cache --dry-run` ничего не удаляет.
- Huey-таска вызывает сервис очистки.

## Файлы, которые будут затронуты

- `movie_filter_pro/settings.py` — лимиты и logger.
- `core/image_cache_maintenance.py` — новый сервис.
- `core/tasks.py` — periodic cleanup.
- `core/management/commands/clean_image_cache.py` — команда.
- `movie_filter_pro/huey.py` — импорт `core.tasks`.
- `vault/services/image_cache.py` — touch при выдаче из кеша.
- `moviefilter/api.py` — touch Kinozal-постеров при отдаче.
- `docs/VAULT-IMAGE-CACHING.md` — раздел про eviction.
- Тесты в `core/tests/` и `vault/tests/`.

Если план подходит — для реализации нужно переключиться на обычного агента (не Plan mode).