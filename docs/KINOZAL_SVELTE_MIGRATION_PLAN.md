# Kinozal Svelte Migration Plan

## Цель

Перенести сценарий работы с `django app kinozal` в новый Svelte UI поэтапно, не ломая существующий Django-интерфейс и не смешивая данные `Kinozal` с `Vault`.

Ключевой принцип:
- `Kinozal` живет в своем отдельном пространстве данных.
- Карточки и модели `Vault` для него не используются.
- Связь `Kinozal <-> Vault` будет делаться позже отдельной логикой.

## Архитектурные договоренности

- Общий shell сайта должен быть независим от `Vault`.
- Sidebar должен быть частью только `Vault`, а не всего приложения.
- `Kinozal` должен жить как отдельный раздел нового UI.
- Legacy Django UI должен оставаться рабочим на всем протяжении переноса.
- Новый frontend должен получать данные через API, а не через перенос HTMX как есть.

## Статус

### Phase 0. Layout / Routing Foundation

- [x] Вынести `sidebar` из глобального layout и сделать его частью только `Vault`.
- [x] Оставить общий верхний shell сайта для всех разделов.
- [x] Добавить верхнюю навигацию: `Kinozal`, `Vault`, `Plex`, `Scan`.
- [x] Добавить правую часть шапки: версия сайта, `TMDB`, `Preferences`, `Login/Logout`, theme toggle.
- [x] Сделать route structure, в которой `Vault` живет отдельно от других разделов.
- [x] Добавить placeholder-страницы `UNDER CONSTRUCTION` для:
  - [x] `Kinozal`
  - [x] `Plex`
  - [x] `Scan`
  - [x] `TMDB`
  - [x] `Preferences`

### Phase 1. Kinozal Read-Only MVP

- [ ] Поднять backend API для чтения списка фильмов `MovieRSS`.
- [ ] Определить API-контракт для infinite pagination.
- [ ] Сделать страницу `/kinozal` в новом UI вместо заглушки.
- [ ] Вывести read-only infinite table без действий, фильтров и сортировки.
- [ ] Показать базовые поля фильма:
  - [ ] poster
  - [ ] title
  - [ ] original title
  - [ ] year
  - [ ] ratings
  - [ ] plot
  - [ ] translate
- [ ] Добавить loading / empty / error states.

### Phase 2. Page Summary And Table Parity

- [ ] Перенести верхние summary-метрики со страницы Django:
  - [ ] last scan
  - [ ] total
  - [ ] high
  - [ ] low
  - [ ] defer
  - [ ] skip
  - [ ] wait trans
  - [ ] trans found
- [ ] Довести визуальную структуру таблицы ближе к Django-версии.
- [ ] Добавить lazy loading для постеров.

### Phase 3. Query State And Filtering

- [ ] Добавить фильтр по priority.
- [ ] Добавить text search.
- [ ] Добавить reverse / sort controls.
- [ ] Синхронизировать состояние страницы с query string.
- [ ] Убедиться, что infinite loading корректно работает вместе с фильтрами.

### Phase 4. Row Actions

- [ ] Перенести действия по строке:
  - [ ] `Open`
  - [ ] `Download`
  - [ ] `Defer`
  - [ ] `Wait trans`
  - [ ] `Hide`
- [ ] Добавить optimistic UI для удаления/обновления строк.
- [ ] Добавить toast-уведомления.

### Phase 5. Download Flow

- [ ] Перенести модалку выбора доступных раздач.
- [ ] Поднять API для поиска вариантов на Kinozal.
- [ ] Поднять API для скачивания torrent-файла.
- [ ] Обработать ошибки:
  - [ ] неверный ответ kinozal
  - [ ] лимит скачиваний
  - [ ] проблемы hotfolder
  - [ ] проблемы с настройками пользователя

### Phase 6. Polish And Stabilization

- [ ] Проверить mobile behavior.
- [ ] Проверить сохранение scroll/infinite state при навигации.
- [ ] Добавить backend-тесты на новые API.
- [ ] Добавить smoke-проверки frontend-сценария.
- [ ] Пройтись по UX-мелочам после первого реального использования.

## Технические ориентиры

### Backend

- Основная модель: `moviefilter.models.MovieRSS`
- Текущий Django entrypoint: `moviefilter/views.py::rss`
- Текущая HTMX-подача таблицы: `moviefilter/htmx_views.py::rss_table_data`

### Frontend

- Route entry: `front/src/routes/kinozal/+page.svelte`
- Общий shell: `front/src/lib/components/SiteShell.svelte`
- Vault-specific sidebar layout: `front/src/lib/components/VaultSidebarLayout.svelte`

## Решения, которые уже приняты

- Не использовать `Vault` movie cards для `Kinozal`.
- Основной UI для `Kinozal` делать как infinite table.
- Не переносить весь функционал за один заход.
- Сначала делать вертикальный срез с реальным route + API + таблицей.

## Ближайший следующий шаг

- Реализовать `Phase 1`: первый read-only API и первую infinite-таблицу на `/kinozal`.
