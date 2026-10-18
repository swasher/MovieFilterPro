# План и подробное описание: синхронизация `vault.Movie` с TMDB

> Исторический план реализации. Указанные ниже HTMX routes и Django templates удалены вместе со старым UI. Текущие frontend-вызовы используют Ninja endpoints из `vault/api.py`, например `/api/vault/movies/{slug}/fetch-tmdb` и `/api/vault/movies/{slug}/fetch-tmdb-confirm`.

## 0) Цель
Сделать сервисную функцию для `vault`, которая:
1. Находит соответствующий объект на TMDB даже без заранее известного `tmdb_id`.
2. Обновляет локальные данные фильма (основные поля, жанры, страны, состав, постер, фото актеров).
3. Доступна из интерфейса кнопкой `Fetch TMDB data` на карточке фильма и в сетках списков.

Ключевой принцип: автоматическое обновление только при высокой уверенности матчинга, иначе выдача пользователю релевантных предложений в модальном окне.

Текущий режим (первая итерация): ручной запуск синка кнопкой.
Будущий режим (в планах): автоматический sync-проход с логированием без модальных окон.

---

## 1) План работ (этапы реализации)

1. Подготовка модели данных `Movie` для связи с TMDB.
2. Реализация алгоритма поиска соответствия (matching) без `tmdb_id`.
3. Реализация сервиса синхронизации полей фильма и связанных сущностей.
4. Добавление endpoint во `vault` для запуска синхронизации по кнопке.
5. Добавление UI-кнопки `Fetch TMDB data` на странице фильма.
6. Добавление компактной кнопки на карточках в списках.
7. Добавление модального окна с релевантными кандидатами TMDB для ambiguous-case.
8. Реализация очистки orphan-персон после синхронизации.
9. Добавление компактного, читаемого лога синхронизации.
10. Добавление минимальных тестов на matching и sync.
11. Проверка вручную на реальных фильмах из текущей базы (movie/series/anime).

---

## 2) Подробное техническое описание

## 2.1. Изменения модели (минимально необходимые)

Проблема: в текущей `vault.models.Movie` нет `tmdb_id`, поэтому повторные вызовы будут всегда искать заново.

Предлагаемые поля в `Movie`:
1. `tmdb_id` (`PositiveIntegerField`, `null=True`, `blank=True`, `db_index=True`)
2. `tmdb_media_type` (`CharField`, choices: `movie`, `tv`, `null=True`, `blank=True`)
3. `tmdb_last_synced_at` (`DateTimeField`, `null=True`, `blank=True`)

Обязательное использование существующих полей:
1. `Movie.source` при успешном sync выставляется в `Movie.Source.TMDB`.
2. `Movie.movie_type` учитывается при выборе порядка поиска (`movie_search` vs `tv_search`) и при маппинге результата TMDB.

Замечание по unique:
1. На первом этапе не ставим жесткий `unique` на `tmdb_id`, чтобы не ломаться на дублях в локальной базе.
2. При необходимости позже добавим контроль уникальности парой (`tmdb_id`, `tmdb_media_type`).

---

## 2.2. Алгоритм поиска соответствия на TMDB (без id)

Источник для базовых эвристик: `assign_tmdb_ids.py` (strict match + alt titles + окно по году).

### Нормализация строк
1. lower-case
2. удаление пунктуации
3. `ё -> е`
4. схлопывание пробелов
5. trim

### Генерация запросов
Для каждого фильма формируем:
1. `query_original` = `original_title` (если есть)
2. `query_localized` = `title` (если есть)
3. годы поиска: `[year, year-1, year+1]` (если год задан), иначе без года

Порядок endpoint по `Movie.movie_type`:
1. `movie/cartoon` -> сначала `movie_search`, потом `tv_search`.
2. `series/show` -> сначала `tv_search`, потом `movie_search`.
3. `anime` -> оба поиска сразу.

### Оценка кандидатов (scoring)
1. Точное совпадение `original_title` с `original_title/original_name`: +60
2. Точное совпадение `title` с `title/name`: +50
3. Совпадение с `alternative_titles`: +35
4. Разница по году:
5. 0 лет: +20
6. 1 год: +10
7. >1 года: 0
8. Совпадение ожидаемого media type (`movie`/`tv`): +10

### Принятие решения (ручной режим)
1. `score >= 90` и лучший кандидат единственный -> авто-выбор и sync.
2. Если кандидаты близки (разница < 15) -> открываем модальное окно с top-N (например 5) и ручным выбором.
3. Если релевантных кандидатов нет -> показываем понятную ошибку, данные не меняем.

### Будущий авто-режим (в планах)
1. Без модалок, только авто-выбор по порогам.
2. Все ambiguous/failed cases пишутся в лог короткими строками.

---

## 2.3. Сервис синхронизации данных фильма

Новый сервис: `vault/services/tmdb_movie_sync_service.py`

Публичный метод:
`TMDBMovieSyncService.sync_movie(movie: Movie, force_rematch: bool = False, selected_candidate: Candidate | None = None) -> SyncResult`

### Поток выполнения
1. Проверить TMDB credentials через `UserPreferences.get()` и `tmdb_adapter.client_singleton.get_tmdb_client()`.
2. Если у фильма уже есть `tmdb_id` и `force_rematch=False`: грузим детали напрямую.
3. Иначе запускаем matching (п.2.2).
4. Если ambiguous и `selected_candidate` не передан: вернуть `SyncResult` c `needs_user_choice=True` и списком кандидатов.
5. При выборе кандидата сохранить `tmdb_id` + `tmdb_media_type`.
6. Грузим полные детали (`tmdb.movie(...)` или `tmdb.tv_show(...)`).
7. Обновляем поля `Movie`, ставим `source = Movie.Source.TMDB`, обновляем `tmdb_last_synced_at`.
8. Пересобираем `genres` и `countries`.
9. Пересобираем `MoviePerson` и обновляем `Person`.
10. Запускаем очистку orphan-персон.
11. Возвращаем структурированный результат.

### Какие поля обновляем в `Movie`
1. `title`
2. `original_title`
3. `description` (overview)
4. `year`
5. `release_date`
6. `duration` (`runtime` или первое значение из `episode_run_time`)
7. `poster` (`poster_path`, как ссылка/путь TMDB)
8. `trailer_url` (youtube trailer, если найден)
9. `status` (через маппинг TMDB status -> локальный enum)
10. `is_ongoing`, `year_end`, `seasons_count`, `episodes_count` (для tv)
11. `budget`, `box_office` (для movie)
12. `movie_type` (если нужно корректируем по факту media type)

### Поля, которые НЕ трогаем
1. `imdb_rating`, `imdb_votes` (не подменяем на TMDB vote).
2. `UserMovie`, пользовательские списки, заметки, оценки.

### Обновление `Genre`/`Country`
1. Жанры: `get_or_create(name=...)`, затем `movie.genres.set(...)`.
2. Страны: используем `core.Country` (не `moviefilter.Country`), поиск по `code`, fallback по `name`, затем `movie.countries.set(...)`.

### Обновление `Person`/`MoviePerson` и фото
1. Пересобираем `movie.movie_persons` из TMDB cast/crew.
2. Для `Person` делаем upsert с приоритетом `tmdb_id`, потом `imdb_id`.
3. Обновляем `person.photo` из TMDB `profile_path` (сохраняем ссылку/путь, как в текущей модели).
4. Маппинг ролей:
5. cast -> `actor` (с `character_name`, `order`)
6. crew `Director` -> `director`
7. crew `Producer/Executive Producer` -> `producer`
8. crew `Writer/Screenplay/Story` -> `writer`
9. crew `Original Music Composer` -> `composer`
10. crew `Director of Photography` -> `operator`
11. crew `Editor` -> `editor`

### Очистка orphan-персон
1. После sync удаляем персон, у которых нет `person_movies`.
2. Защита: не удаляем персон, если они в `FavoritePerson`.
3. Вести счетчик удаленных orphan-персон и писать его в итог лога.

---

## 2.4. Endpoint, модалка и кнопки UI

### Backend
Добавить endpoints во `vault`:
1. `POST /vault/htmx/fetch-tmdb/` (`vault:htmx_fetch_tmdb_data`) - старт синка.
2. `POST /vault/htmx/fetch-tmdb-confirm/` (`vault:htmx_fetch_tmdb_confirm`) - подтверждение выбранного кандидата из модалки.

Ответы:
1. success -> компактный success block с коротким summary.
2. ambiguous -> HTML для модалки с кандидатами и кнопками выбора.
3. error -> компактный error block с причиной.

### Frontend
1. `movie_detail.html`: кнопка `Fetch TMDB data` + блок результата + модалка кандидатов.
2. `movie_list.html`: компактная кнопка/иконка синка на карточке.
3. `list_detail.html`: компактная кнопка/иконка синка на карточке.

---

## 2.5. Компактный лог синхронизации

Лог короткими строками, без многословия.

Формат:
1. `SYNC_START | movie_id=... | title="..." | orig="..." | year=...`
2. `MATCH_FOUND | candidates=N | top=[id:score,...]`
3. `MATCH_SELECTED | tmdb_id=... | media=movie|tv | reason=auto|manual`
4. `SYNC_APPLY | updated=field1,field2,... | cast=... | crew=...`
5. `ORPHAN_CLEANUP | deleted=...`
6. `SYNC_DONE | status=ok|error | msg="..."`

Цель: чтобы в случае ошибки сразу было видно, на каком шаге и почему.

---

## 2.6. Ошибки и защита от порчи данных

Обязательные кейсы:
1. Нет TMDB API key -> понятная ошибка в UI.
2. Кандидаты не найдены -> без изменений в БД.
3. Ambiguous без выбора -> показываем модалку, без изменений в БД.
4. Ошибка TMDB API/timeout -> без частично записанных связей.

Технически:
1. Операция sync под `transaction.atomic()`.
2. Логируем шаги в `logs/debug.log`.

---

## 2.7. Тестирование (минимум)

Добавить тесты:
1. Нормализация названия.
2. Scoring: exact match выигрывает у частичного.
3. Ambiguous case возвращает кандидатов для модалки.
4. Sync обновляет `Movie`, `Genre`, `core.Country`, `MoviePerson`, `Person.photo`.
5. Sync не трогает `UserMovie`.
6. Очистка orphan-персон удаляет только безопасные orphan-записи.

Рекомендуемый путь:
`vault/tests/test_tmdb_movie_sync_service.py`

---

## 2.8. Файлы, которые будут изменены на этапе реализации

1. `vault/models.py` (+ миграция)
2. `vault/services/tmdb_movie_sync_service.py` (новый)
3. `vault/services/person_cleanup_service.py` (новый или часть sync-сервиса)
4. `vault/views.py` (новые HTMX views)
5. `vault/urls.py` (новые routes)
6. `vault/templates/vault/movie_detail.html` (кнопка + результат + модалка)
7. `vault/templates/vault/movie_list.html` (кнопка sync на карточке)
8. `vault/templates/vault/list_detail.html` (кнопка sync на карточке)
9. `vault/tests/test_tmdb_movie_sync_service.py` (новый)

---

## 3) Критерии готовности (Definition of Done)

1. По кнопке на фильме запускается sync.
2. Для уверенного совпадения фильм получает `tmdb_id` и обновленные данные.
3. Для неуверенного совпадения открывается модалка с релевантными кандидатами.
4. Кнопка синка есть и в деталке, и на карточках в списках.
5. `Movie.source` корректно переключается в `tmdb`.
6. Страны обновляются через `core.Country`.
7. Постер фильма и фото актеров обновляются ссылками TMDB.
8. После sync выполняется безопасная очистка orphan-персон.
9. Лог компактный и информативный.
10. Пользовательские статусы/оценки/заметки не повреждаются.

---

## 4) Вопросы на подтверждение перед реализацией

1. Для orphan-cleanup оставляем правило "не удалять персон из `FavoritePerson`"?
2. Для кнопок в `movie_list` и `list_detail` делаем только иконку с tooltip или текстовую мини-кнопку?
