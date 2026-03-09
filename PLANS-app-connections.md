# План: Kinozal download -> TMDB -> Vault

## Цель

После успешного скачивания `.torrent` из Kinozal:

- найти соответствующий фильм на TMDB;
- добавить или переиспользовать запись в `Vault`;
- присвоить фильму статус `Буду смотреть`;
- сделать процесс идемпотентным;
- сохранить подробную историю шагов в отдельной таблице `Vault` и показать её на новом route во фронте.

## Быстрый аудит текущего состояния

### 1. Точка триггера и потеря контекста

- В `moviefilter/templates/partials/rss-table.html` кнопка `Download` открывает модалку по `f.id`, то есть по `MovieRSS.pk`.
- В `moviefilter/htmx_views.py:kinozal_download` этот `pk` используется для поиска вариантов раздачи.
- Но в `moviefilter/templates/partials/kinozal_download.html` финальная кнопка скачивания вызывает `get_torrent_file` уже только с `m.id`, то есть с `torrent_id` выбранной раздачи.
- В результате после записи `.torrent` текущий код уже не знает, от какого `MovieRSS` был инициирован сценарий.

Это главное логическое расхождение, которое надо закрыть до любой интеграции с `Vault`.

### 2. `imdb_id` и `kinopoisk_id` в RSS уже есть, но сохраняются неидеально

- `kinozal_scan/parse.py::get_details` действительно парсит `imdb_id` и `kinopoisk_id`.
- У `moviefilter.models.MovieRSS` поля для них уже существуют.
- Запись в RSS сейчас идёт через `MovieRSS.objects.get_or_create(..., defaults=dataclasses.asdict(m))`.

Следствие:

- при первичном создании строки `imdb_id/kinopoisk_id` попадают в БД;
- если строка `MovieRSS` уже существовала, а идентификаторы появились позже, они не backfill-ятся и останутся `NULL`.

Для вашей фичи это важно: нельзя просто "предположить", что `imdb_id` всегда уже лежит в `MovieRSS`.

### 3. Типы полей под внешние ID уже выглядят как техдолг

- `MovieRSS.kinopoisk_id` сейчас `PositiveSmallIntegerField`.
- Для Kinopoisk это слишком узкое поле и его нельзя тащить дальше в `Vault` в таком виде.
- Аналогичный риск есть и у `MovieRSS.kinozal_id`, но для текущей задачи блокером является именно `kinopoisk_id`.

Рекомендация для плана: новый `kinopoisk_id` в `Vault` делать не `PositiveSmallIntegerField`, а как минимум `PositiveIntegerField` или `CharField`, если хотим не зависеть от формата.

### 4. В `Vault` уже есть TMDB-стек, но не хватает внешних идентификаторов и orchestration-слоя

- `vault.Movie` уже хранит `tmdb_id`, `tmdb_media_type`, `tmdb_last_synced_at`.
- `vault.services.tmdb_movie_import_service.TMDBMovieImportService` уже умеет импортировать фильм по `tmdb_id`.
- `vault.services.tmdb_movie_sync_service.TMDBMovieSyncService` уже умеет синкать локальную запись из TMDB.
- `vault.services.movie_status_service.MovieStatusService` уже умеет выставлять статус `will_watch`.

Но:

- в `vault.Movie` пока нет полей `imdb_id` и `kinopoisk_id`;
- `TMDBMovieMatchingService` сейчас матчит только по `title/original_title/year`;
- прямого orchestration-слоя для сценария `скачали торрент -> нашли/добавили в Vault -> выставили статус` пока нет.

### 5. Важный техдолг вокруг точки скачивания

- Логика скачивания `.torrent` дублируется в `moviefilter/htmx_views.py` и `moviefilter/api.py`.
- `get_torrent_file` выполняет side effects через `GET`.
- На HTMX-входе нет отдельного application service, поэтому туда легко "налепить" ещё один обход сервисного слоя `Vault`.

Для этой задачи лучше не добавлять бизнес-логику прямо во view.

## Предлагаемое целевое решение

### Ключевое решение

Триггер остаётся там, где вы хотите: сразу после успешной записи `.torrent` в `moviefilter/htmx_views.py:get_torrent_file`.

Но сама бизнес-операция должна быть вынесена в отдельный application service, который:

1. принимает `movie_rss_id`, `torrent_id`, `user`, путь к сохранённому файлу;
2. пишет audit events;
3. ищет или создаёт фильм в `Vault`;
4. выставляет статус `Буду смотреть`;
5. гарантирует идемпотентность.

Это же приложение/сервис потом сможет переиспользоваться и из текущего API (`moviefilter/api.py`), чтобы не держать две разные реализации.

## Целевой flow

1. Пользователь нажимает `Download` у фильма в RSS.
2. Модалка получает и сохраняет `movie_rss_id`.
3. Пользователь выбирает конкретную раздачу.
4. `get_torrent_file` получает одновременно:
   - `movie_rss_id`;
   - `torrent_id` выбранной раздачи.
5. `.torrent` успешно сохраняется на диск.
6. Сразу после этого вызывается новый orchestration service.
7. Сервис пишет событие `download_saved`.
8. Сервис пытается найти уже существующий фильм в `Vault`.
9. Если не нашёл локально, ищет соответствие в TMDB:
   - сначала по `imdb_id`;
   - если `imdb_id` нет, тогда по `title/original_title + year`.
10. Если найден уверенный матч:
   - импортирует или переиспользует `vault.Movie`;
   - сохраняет в `Vault` `imdb_id` и `kinopoisk_id`;
   - выставляет `MovieStatusService.set_status(..., "will_watch")`.
11. Если матч не найден или неоднозначен:
   - ничего не создаёт "по догадке";
   - пишет детальный event в audit table;
   - завершает сценарий без дублей и без мусорных записей.

## Matching strategy

### Приоритет поиска

1. Уже существующий фильм в `Vault` по `imdb_id`.
2. Уже существующий фильм в `Vault` по `kinopoisk_id`.
3. TMDB lookup по `imdb_id`.
4. Fallback на существующий `TMDBMovieMatchingService` по `title/original_title/year`.

### Почему именно так

- `imdb_id` из Kinozal является самым надёжным ключом для авто-матча.
- `kinopoisk_id` нужен не для поиска в TMDB, а для сохранения связки в локальной БД `Vault` и последующего аудита/аналитики.
- Fallback `title + year` оставляем только как временный путь, который включается при отсутствии `imdb_id`.

### Поведение при ambiguous case

Если матч неуверенный или найдено несколько кандидатов:

- в автоматическом сценарии не импортировать фильм;
- писать событие уровня `warning`;
- финальный статус операции помечать как `needs_manual_resolution`.

Это защищает от тихих ложных совпадений.

## Идемпотентность

### Что именно должно быть идемпотентным

Повторное нажатие `Download` не должно:

- создавать второй `vault.Movie`;
- создавать второй `UserMovie`;
- повторно выставлять новые связи так, чтобы плодились дубли.

### Как это обеспечить

1. До импорта искать уже существующий `Vault`-фильм по `imdb_id`/`kinopoisk_id`.
2. Если фильм уже найден, не импортировать заново, а только переиспользовать.
3. Статус `Буду смотреть` выставлять через `MovieStatusService.set_status(...)`, а не через ручное создание `UserMovie`.
4. События в audit table писать можно и на повторном клике, но результат должен быть `reused` / `already_linked`, а не `created`.

### Что не стоит делать

Не нужно пытаться решать идемпотентность только через event table. Она нужна для наблюдаемости, а не как единственный источник истины.

## Изменения в моделях

### 1. `moviefilter.MovieRSS`

Нужно:

- расширить тип `kinopoisk_id`;
- при необходимости добавить мягкий update-path для уже существующих строк, чтобы `imdb_id/kinopoisk_id` дописывались, если раньше были пустыми.

### 2. `vault.Movie`

Добавить:

- `imdb_id` (`CharField`, `null=True`, `blank=True`, `db_index=True`);
- `kinopoisk_id` (`PositiveIntegerField` или `CharField`, `null=True`, `blank=True`, `db_index=True`).

Не рекомендую делать эти поля сразу `unique=True` в первой итерации, чтобы не ловить миграционные конфликты на уже существующих данных. Лучше сначала `db_index`, затем отдельно проверить данные.

### 3. Новая audit table в `Vault`

Рекомендованное имя: `VaultConnectionEvent`.

Поля:

- `operation_id` (`UUIDField`, `db_index=True`) для группировки шагов одной попытки;
- `source` (`kinozal_download`);
- `event_type`;
- `level` (`info/success/warning/error`);
- `message`;
- `movie_rss` (`FK -> MovieRSS`, nullable);
- `vault_movie` (`FK -> vault.Movie`, nullable);
- `user` (`FK -> auth.User`, nullable);
- `rss_kinozal_id`;
- `torrent_kinozal_id`;
- `imdb_id`;
- `kinopoisk_id`;
- `tmdb_id`;
- `payload` (`JSONField`, nullable);
- `created_at`.

Такой формат удобнее, чем одна "итоговая" запись: он позволит видеть всю цепочку шагов внутри одной операции.

## Где должен жить новый orchestration service

Рекомендация: отдельный сервис в `vault/services/`, например:

- `vault/services/kinozal_download_import_service.py`

Причина:

- цель сценария именно в том, чтобы создать/обновить данные `Vault`;
- внутри сервиса уже можно безопасно переиспользовать `TMDBMovieImportService`, `TMDBMovieSyncService`, `MovieStatusService`;
- view из `moviefilter` останется тонким триггером, а не местом, где смешаны HTTP, файловая система, TMDB и `Vault`.

## Детальный план реализации

### Этап 1. Удержать `MovieRSS` контекст до финального скачивания

Файлы:

- `moviefilter/templates/partials/rss-table.html`
- `moviefilter/templates/partials/kinozal_download.html`
- `moviefilter/htmx_views.py`

Сделать:

- передавать в модалку `movie_rss_id`;
- передавать его дальше в финальный action скачивания;
- в `get_torrent_file` иметь доступ и к `movie_rss_id`, и к `torrent_id`.

### Этап 2. Выделить общий сервис скачивания `.torrent`

Файлы:

- `moviefilter/htmx_views.py`
- `moviefilter/api.py`
- возможно новый helper/service в `moviefilter`

Сделать:

- вынести общий код записи torrent-файла в одно место;
- вызывать post-download hook из HTMX и API одинаково;
- не плодить вторую реализацию скачивания.

### Этап 3. Починить сохранение внешних идентификаторов в RSS

Файлы:

- `kinozal_scan/parse.py`
- `moviefilter/models.py`
- миграции `moviefilter`

Сделать:

- расширить `kinopoisk_id`;
- обновить persistence-path так, чтобы уже существующий `MovieRSS` мог получить `imdb_id/kinopoisk_id`, если раньше они были пустыми.

### Этап 4. Расширить модель `Vault`

Файлы:

- `vault/models.py`
- миграции `vault`

Сделать:

- добавить `imdb_id`;
- добавить `kinopoisk_id`;
- подготовить индексы под локальный re-use и идемпотентность.

### Этап 5. Добавить TMDB lookup по `imdb_id`

Файлы:

- `vault/services/tmdb_movie_matching_service.py`
- или новый узкий helper в `tmdb_adapter`

Сделать:

- добавить отдельный путь `find by imdb_id` перед `title/year`;
- если `tmdbapis` не даёт готового метода, оформить это в инфраструктурном слое `tmdb_adapter`, а не в view.

### Этап 6. Реализовать orchestration service `Kinozal -> Vault`

Файлы:

- `vault/services/kinozal_download_import_service.py` (новый)
- `moviefilter/htmx_views.py`
- `moviefilter/api.py`

Сделать:

- создать сервис уровня application layer;
- на вход принимать `movie_rss_id`, `torrent_id`, `user`, `saved_to`;
- писать события;
- искать/импортировать `Vault`-фильм;
- выставлять `will_watch`.

### Этап 7. Добавить audit API

Файлы:

- `vault/api.py`

Сделать:

- endpoint списка событий, например `/api/vault/connection-events`;
- фильтры по времени, уровню, source, `movie_rss_id`, `operation_id`;
- пагинацию или хотя бы limit/offset.

### Этап 8. Добавить route во фронте Svelte

Файлы:

- `front/src/routes/(vault)/connections/+page.server.ts`
- `front/src/routes/(vault)/connections/+page.svelte`
- `front/src/routes/(vault)/+layout.server.ts`
- `front/src/lib/template-data.ts`
- при необходимости `vault/api.py:/sidebar`

Сделать:

- отдельную страницу с таблицей событий;
- колонками: время, шаг, результат, исходный фильм, `torrent_id`, `tmdb_id`, `vault_movie`, сообщение;
- добавить route в sidebar.

Legacy Django UI для этой таблицы не нужен, если задача ограничивается новым Svelte frontend.

## Тесты

### Обязательные backend-тесты

- успешный сценарий: есть `imdb_id`, найден TMDB, фильм добавлен/переиспользован, статус `will_watch` выставлен;
- повторный `Download`: второй `vault.Movie` не создаётся, второй `UserMovie` не создаётся;
- fallback: `imdb_id` отсутствует, используется `title + year`;
- ambiguous TMDB match: фильм не создаётся, событие пишется;
- not found: фильм не создаётся, событие пишется;
- существующий `MovieRSS` без ID получает `imdb_id/kinopoisk_id` при повторном проходе сканера;
- audit API возвращает события в ожидаемом порядке.

### Желательные фронтовые проверки

- route с таблицей событий открывается;
- sidebar показывает новый пункт;
- строка события даёт достаточно контекста для диагностики.

## Открытые вопросы и допущения

### 1. Lookup по `imdb_id` в `tmdbapis`

Это нужно подтвердить на этапе реализации.

- Если библиотека уже умеет `find`/`external id lookup`, используем её.
- Если нет, добавляем тонкий adapter-метод в `tmdb_adapter`.

### 2. Что делать с неуверенным матчем

Для первой версии рекомендую:

- не импортировать автоматически;
- только логировать в audit table;
- оставить ручное подтверждение как follow-up.

### 3. Нужно ли отдельное поле связи `MovieRSS -> Vault.Movie`

Для первой версии не обязательно.

- Идемпотентность можно обеспечить через внешние идентификаторы и re-use существующего `Vault.Movie`.
- Если позже понадобится удобная трассировка "какой RSS породил какой Vault movie", это можно добавить отдельной связью поверх audit table.

## Риски и техдолг, которые нельзя забыть

- `MovieRSS` сейчас считается уникальным по `title/original_title/year`, а не по `kinozal_id`; это мешает корректному enrichment уже существующих строк.
- `GET` с side effects в `get_torrent_file` лучше перевести на `POST`, даже если имя view останется прежним.
- Без `operation_id` в audit table дебажить многошаговые ошибки будет неудобно.
- Если положить всю бизнес-логику обратно в HTMX-view, появится третий независимый сценарий рядом с `moviefilter/api.py`, и техдолг вырастет.

## Критерии готовности

- После успешной записи `.torrent` система автоматически пытается связать `MovieRSS` с `Vault`.
- При уверенном матче фильм оказывается в `Vault` со статусом `Буду смотреть`.
- Повторное нажатие `Download` не создаёт дубликаты.
- `imdb_id` и `kinopoisk_id` доходят до `Vault`.
- В `Vault` есть отдельная DB-таблица событий.
- Во фронте есть route, где видно всю историю попыток и причины ошибок.
