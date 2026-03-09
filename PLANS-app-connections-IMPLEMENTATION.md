# Implementation Plan: Kinozal download -> TMDB -> Vault

Использовать вместе с `PLANS-app-connections.md`.

Правило ведения:

- Закрывать чекбоксы только после фактического выполнения и локальной проверки шага.
- Если по ходу реализации меняется решение, сначала обновить оба документа, потом код.
- Не обходить service layer прямой логикой во view, если это не зафиксировано отдельно.

## Фаза 0. Подтверждение текущей базы для реализации

- [x] Подтвердить, что `get_torrent_file` сейчас теряет `MovieRSS` контекст и требует передачи `movie_rss_id` до финального шага скачивания.
- [x] Подтвердить, что `MovieRSS.imdb_id` и `MovieRSS.kinopoisk_id` реально парсятся из Kinozal и сохраняются только при первичном `get_or_create`.
- [x] Подтвердить, что `Vault` уже содержит переиспользуемые сервисы `TMDBMovieImportService`, `TMDBMovieSyncService`, `MovieStatusService`.
- [x] Проверить, есть ли в `tmdbapis` готовый lookup по `imdb_id`; если нет, зафиксировать adapter fallback в коде и при необходимости обновить план.

## Фаза 1. Удержать контекст `MovieRSS` до скачивания торрента

- [x] Обновить HTMX flow так, чтобы при открытии модалки сохранялся `movie_rss_id`.
- [x] Протащить `movie_rss_id` до кнопки выбора конкретной раздачи в `kinozal_download.html`.
- [x] Сделать так, чтобы `get_torrent_file` получал и `movie_rss_id`, и `torrent_id`.
- [x] Не сломать текущий UX модалки `Download`.

## Фаза 2. Выделить общий путь скачивания `.torrent`

- [x] Вынести общий код скачивания и записи `.torrent` в единый helper/service.
- [x] Перевести `moviefilter/htmx_views.py` на использование общего helper/service.
- [x] Перевести `moviefilter/api.py` на использование того же helper/service.
- [x] Подготовить post-download hook, который можно вызывать и из HTMX, и из API.
- [x] По возможности перевести конечный action скачивания с `GET` на `POST`; если это откладывается, явно зафиксировать техдолг.

## Фаза 3. Починить сохранение внешних идентификаторов в RSS

- [x] Расширить тип `MovieRSS.kinopoisk_id` до безопасного формата.
- [x] Добавить миграцию для изменения поля `MovieRSS.kinopoisk_id`.
- [x] Исправить persistence-path сканера так, чтобы уже существующий `MovieRSS` мог получать `imdb_id/kinopoisk_id`, если раньше поля были пустыми.
- [x] Проверить, что повторный проход сканера не ломает текущую логику `exist_in_kinozal`.

## Фаза 4. Подготовить `Vault` к внешним идентификаторам и audit trail

- [x] Добавить в `vault.Movie` поле `imdb_id`.
- [x] Добавить в `vault.Movie` поле `kinopoisk_id`.
- [x] Добавить индексы под локальный re-use и идемпотентность.
- [x] Создать новую таблицу `VaultConnectionEvent` или согласованное финальное имя.
- [x] Добавить миграцию для новой audit table.
- [x] Убедиться, что модель audit table хранит `operation_id`, ссылки на `MovieRSS` и `Vault Movie`, внешние ID, уровни событий и `payload`.

## Фаза 5. Добавить TMDB matching по `imdb_id`

- [x] Реализовать lookup по `imdb_id` перед fallback на `title/year`.
- [x] Если нужен новый инфраструктурный helper, разместить его в `tmdb_adapter`, а не во view.
- [x] Обновить matching strategy так, чтобы `imdb_id` был первым приоритетом авто-матча.
- [x] Сохранить существующий fallback `title/original_title/year` для случаев без `imdb_id`.
- [x] Явно обработать ambiguous / not found сценарии без автоматического создания мусорных записей.

## Фаза 6. Реализовать orchestration service `Kinozal -> Vault`

- [x] Создать новый application service в `vault/services/` для post-download сценария.
- [x] На вход сервиса передавать `movie_rss_id`, `torrent_id`, `user`, `saved_to`.
- [x] В начале операции создавать `operation_id`.
- [x] Логировать ключевые шаги в audit table: старт, сохранение torrent, поиск локального фильма, TMDB lookup, импорт/reuse, выставление статуса, ошибки.
- [x] Сначала искать существующий `Vault Movie` по `imdb_id`.
- [x] Затем искать существующий `Vault Movie` по `kinopoisk_id`.
- [x] При отсутствии локальной записи запускать TMDB lookup.
- [x] При уверенном совпадении импортировать или переиспользовать `Vault Movie`.
- [x] Сохранять `imdb_id` и `kinopoisk_id` в `vault.Movie`.
- [x] Выставлять статус `Буду смотреть` через `MovieStatusService.set_status(..., "will_watch")`.
- [x] Обеспечить идемпотентность повторного `Download` без дублей `Movie`, `UserMovie` и лишних импортов.
- [x] Подключить вызов orchestration service из `moviefilter/htmx_views.py`.
- [x] Подключить тот же вызов из `moviefilter/api.py`, если API тоже должен поддерживать сценарий.

## Фаза 7. Добавить audit API

- [x] Добавить endpoint списка событий в `vault/api.py`.
- [x] Добавить фильтры по времени, уровню, source, `movie_rss_id`, `operation_id`.
- [x] Добавить limit/offset или другой минимальный способ не тащить весь лог сразу.
- [x] Убедиться, что endpoint требует аутентификацию и не использует fallback-пользователя.

## Фаза 8. Добавить route во фронте Svelte

- [x] Создать route `front/src/routes/(vault)/connections/+page.server.ts`.
- [x] Создать route `front/src/routes/(vault)/connections/+page.svelte`.
- [x] Подключить новый route к sidebar навигации.
- [x] Показать в таблице минимум: время, шаг, результат, исходный RSS-фильм, `torrent_id`, `tmdb_id`, `vault movie`, сообщение.
- [x] Сделать страницу пригодной для диагностики ошибок без открытия DevTools.
- [x] Не ломать существующую навигацию и паттерны текущего Svelte frontend.

## Фаза 9. Тесты и проверка идемпотентности

- [x] Добавить backend-тест на успешный сценарий с `imdb_id`.
- [x] Добавить backend-тест на fallback по `title + year`, если `imdb_id` отсутствует.
- [x] Добавить backend-тест на ambiguous TMDB match без автоматического импорта.
- [x] Добавить backend-тест на `not_found` сценарий с записью события.
- [x] Добавить backend-тест на идемпотентность повторного `Download`.
- [x] Добавить backend-тест на обновление уже существующего `MovieRSS`, у которого раньше не было `imdb_id/kinopoisk_id`.
- [x] Добавить backend-тест на audit API.
- [ ] Проверить вручную, что новый фронтовый route показывает события и помогает дебажить пайплайн.

## Фаза 10. Финальная сверка с критериями готовности

- [x] После успешной записи `.torrent` автоматически стартует связка `Kinozal -> Vault`.
- [x] При уверенном матче фильм оказывается в `Vault` со статусом `Буду смотреть`.
- [x] Повторное нажатие `Download` не создаёт дубликаты.
- [x] `imdb_id` и `kinopoisk_id` доходят до `Vault`.
- [x] Audit table содержит всю цепочку шагов одной операции.
- [x] Во фронте есть рабочий route для просмотра истории событий.
- [x] Оба документа плана актуализированы по фактической реализации.
