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

- [x] Поднять backend API для чтения списка фильмов `MovieRSS`.
- [x] Определить API-контракт для infinite pagination.
- [x] Сделать страницу `/kinozal` в новом UI вместо заглушки.
- [x] Вывести read-only infinite table без действий, фильтров и сортировки.
- [x] Показать базовые поля фильма:
  - [x] poster
  - [x] title
  - [x] original title
  - [x] year
  - [x] ratings
  - [x] plot
  - [x] translate
- [x] Добавить loading / empty / error states.

### Phase 2. Page Summary And Table Parity

- [x] Перенести верхние summary-метрики со страницы Django:
  - [x] last scan
  - [x] total
  - [x] high
  - [x] low
  - [x] defer
  - [x] skip
  - [x] wait trans
  - [x] trans found
- [x] Довести визуальную структуру таблицы ближе к Django-версии.
- [x] Добавить lazy loading для постеров.

### Phase 3. Query State And Filtering

- [x] Добавить фильтр по priority.
- [x] Добавить text search.
- [x] Добавить reverse / sort controls.
- [x] Синхронизировать состояние страницы с query string.
- [x] Убедиться, что infinite loading корректно работает вместе с фильтрами.

### Phase 4. Row Actions

- [x] Перенести действия по строке:
  - [x] `Open`
  - [x] `Download`
  - [x] `Defer`
  - [x] `Wait trans`
  - [x] `Hide`
- [x] Добавить optimistic UI для удаления/обновления строк.
- [x] Добавить toast-уведомления.

### Phase 5. Download Flow

- [x] Перенести модалку выбора доступных раздач.
- [x] Поднять API для поиска вариантов на Kinozal.
- [x] Поднять API для скачивания torrent-файла.
- [x] Обработать ошибки:
  - [x] неверный ответ kinozal
  - [x] лимит скачиваний
  - [x] проблемы hotfolder
  - [x] проблемы с настройками пользователя

### Phase 6. Polish And Stabilization

- [ ] Проверить mobile behavior.
- [ ] Проверить сохранение scroll/infinite state при навигации.
- [x] Добавить backend-тесты на новые API.
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

- Реализовать `Phase 6`: mobile behavior, scroll state, тесты и финальную полировку UX.
