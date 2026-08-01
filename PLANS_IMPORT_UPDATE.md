# План: импорт HIDE (SKIP) фильмов из Kinozal в Vault

## Цель
После основного импорта Kinorium CSV в Vault, добавить в `import_kinorium_csv.py` новый шаг,
который обрабатывает фильмы из Kinozal (таблица `MovieRSS`), помеченные пользователем как
**Hide** (`priority = SKIP`).

Если такого фильма **нет** в Vault — он заносится в Vault с пометкой «Не буду смотреть»
(`UserMovie.watch_status = SKIP`). Если фильм **уже есть** в Vault — пропускаем.

## Согласованные решения
1. **Размещение** — прямо в `vault/management/commands/import_kinorium_csv.py`, в конце `handle()`.
2. **Сопоставление Kinozal ↔ Vault** — только локальное, «умное», по `title` / `original_title` / `year`:
   - Полное совпадение: `title + original_title + year`
   - Одно частичное совпадение (fallback): `title + year` ИЛИ `title + original_title` ИЛИ `original_title + year`
   - Логика повторяет `kinozal_scan/checks.py::exist_in_kinorium`.
3. **imdb_id не используется** для сопоставления с Vault (в Kinorium/Vault нет imdb_id;
   imdb_id применим только для TMDB API, что дорого для тысяч фильмов).
4. **Наполнение создаваемого Movie** — только базовое:
   `title`, `original_title`, `year`, `imdb_id`, `kinopoisk_id`, `poster`, `description`.
   Без genres / countries / director / actors / Person / MoviePerson.
5. **Пользователь** — только `id=1` (тот же `_ensure_user()`).
6. **Если фильм найден в Vault** — просто пропускаем, статус не трогаем.
7. **Логирование** — человекочитаемые строки в файл `logs/debug.log`
   (logger `debug_logger`, уже настроен в `settings.py`).
8. **Сводка** — в терминал через `self.stdout` (кол-во обработано, создано, пропущено, без года).

## Алгоритм (шаг 6 в `handle()`)

1. Выбрать все `MovieRSS.objects.filter(priority=SKIP)`.
2. Для каждого `rss`:
   - Определить `year` как первые 4 цифры (год может быть диапазоном `1982-1994`).
   - Попытаться найти Vault Movie:
     - Полное совпадение `title + original_title + year`
     - Если нет — частичное совпадение (по очереди):
       - `title + original_title`
       - `title + year`
       - `original_title + year`
   - **Найден** → залогировать «уже в Vault, пропускаем», счётчик `skipped_existing`.
   - **Не найден** → создать `Movie` (базовое наполнение) + `UserMovie(watch_status=SKIP)`,
     залогировать «добавлен», счётчик `created`.
3. Вывести сводку в терминал.
