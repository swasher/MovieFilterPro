# VAULT TMDB Sync Implementation

## Phase 1: Data Model
- [x] Добавить в `vault.Movie` поля: `tmdb_id`, `tmdb_media_type`, `tmdb_last_synced_at`
- [x] Создать и применить миграцию
- [x] Проверить, что `Movie.source` и `Movie.movie_type` не ломаются после миграции

## Phase 2: Matching Engine
- [x] Реализовать нормализацию названий
- [x] Реализовать поиск кандидатов через `movie_search` и `tv_search`
- [x] Реализовать scoring кандидатов
- [x] Реализовать режимы результата: `auto_match`, `needs_user_choice`, `not_found`
- [x] Добавить формирование top-N релевантных кандидатов для модалки

## Phase 3: TMDB Sync Service
- [x] Создать `vault/services/tmdb_movie_sync_service.py`
- [x] Реализовать загрузку деталей по `tmdb_id + media_type`
- [x] Реализовать обновление полей `Movie` (включая `source=tmdb`)
- [x] Реализовать обновление `genres`
- [x] Реализовать обновление `countries` через `core.Country`
- [x] Реализовать обновление `poster` (ссылка/путь TMDB)

## Phase 4: Cast and Persons
- [ ] Реализовать пересборку `MoviePerson` из cast/crew
- [ ] Реализовать upsert для `Person` по `tmdb_id/imdb_id`
- [ ] Реализовать обновление `Person.photo` из `profile_path`
- [ ] Реализовать удаление старых связей `MoviePerson` перед пересборкой

## Phase 5: Orphan Cleanup
- [ ] Реализовать очистку orphan-персон после sync
- [ ] Защитить от удаления персон из `FavoritePerson`
- [ ] Добавить счетчик удаленных orphan-персон в результат sync

## Phase 6: HTMX Endpoints
- [ ] Добавить `htmx/fetch-tmdb/` (старт синка)
- [ ] Добавить `htmx/fetch-tmdb-confirm/` (подтверждение выбора из модалки)
- [ ] Добавить обработку `needs_user_choice` и возврат HTML модалки
- [ ] Добавить обработку success/error response блоков

## Phase 7: UI
- [ ] Добавить кнопку `Fetch TMDB data` в `movie_detail.html`
- [ ] Добавить модальное окно выбора кандидата в `movie_detail.html`
- [ ] Добавить компактную кнопку sync в `movie_list.html`
- [ ] Добавить компактную кнопку sync в `list_detail.html`
- [ ] Добавить визуальную индикацию статуса sync (успех/ошибка)

## Phase 8: Logging
- [ ] Добавить компактные log-события: `SYNC_START`, `MATCH_FOUND`, `MATCH_SELECTED`, `SYNC_APPLY`, `ORPHAN_CLEANUP`, `SYNC_DONE`
- [ ] Убедиться, что логи короткие и читаемые
- [ ] Убедиться, что причина ошибки всегда видна в одной строке

## Phase 9: Tests
- [ ] Добавить тесты нормализации и scoring
- [ ] Добавить тест ambiguous-case (возврат кандидатов)
- [ ] Добавить тест обновления `Movie`/`Genre`/`core.Country`/`MoviePerson`/`Person.photo`
- [ ] Добавить тест сохранности `UserMovie`
- [ ] Добавить тест очистки orphan-персон

## Phase 10: Manual Verification
- [ ] Прогнать sync на фильме с точным матчем
- [ ] Прогнать sync на ambiguous фильме и выбрать кандидата в модалке
- [ ] Прогнать sync на фильме без результата
- [ ] Проверить кнопки sync в деталке и карточках списков
- [ ] Проверить компактность логов в `logs/debug.log`
