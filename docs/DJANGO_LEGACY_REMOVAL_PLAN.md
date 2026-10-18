# План удаления старого Django интерфейса

## Исходное решение

Старый Django интерфейс полностью выведен из эксплуатации и удаляется целиком. Не требуется сверять его поведение с Svelte. Цель — убрать только интерфейсный слой и оставшийся исключительно для него код, сохранив backend приложения.

Под «всеми URL» в этом плане понимаются все маршруты Django UI: HTML страницы, формы и HTMX endpoints. Django Ninja API (`/api/...`), `/admin/`, WebSocket и маршруты раздачи статических файлов не являются URL старого интерфейса и в этой задаче сохраняются.

## Порядок работ

### 1. Удалить Django templates

Убрать шаблоны старого UI и его HTML-фрагменты из приложений:

- `core/templates/**`
- `moviefilter/templates/**`
- `vault/templates/**`
- `kinozal_scan/templates/**`
- `kinorium/templates/**`
- `plex/templates/**`
- `tmdb_adapter/templates/**`

Перед удалением выполнить поиск всех `render()`, `template_name`, `{% include %}` и template loader references, чтобы собрать связанные Python-точки и не оставить сломанные ссылки. Если в Django admin или системных письмах используются шаблоны из этих каталогов, отметить их отдельно: они не относятся к UI и не удаляются автоматически.

### 2. Удалить все Django UI URLs

Удалить маршруты страниц и их HTMX endpoints из корневого URLConf и URLConf приложений. Удалить соответствующие `include()` и импорты views. `movie_filter_pro/urls.py` после очистки должен подключать только:

- `/admin/`;
- Ninja API (`core`, `vault`, `kinozal`, `plex`);
- WebSocket routing, если он действительно регистрируется через ASGI отдельно от HTTP URLConf;
- debug-only и static/media служебные маршруты, если они нужны в локальной разработке.

Не удалять Ninja API URLs, Django admin, ASGI/WebSocket маршрутизацию или static/media serving в рамках удаления UI. Это отдельные backend/infra entrypoints.

Интерфейсные URL, найденные при инвентаризации:

| Приложение | Маршруты старого UI |
|---|---|
| `moviefilter` | `/` RSS страница и HTMX маршруты из `moviefilter/urls.py` |
| `vault` | `/vault/**` и unprefixed Vault routes в `movie_filter_pro/urls.py`; HTML и HTMX действия |
| `kinozal_scan` | `/scan_page/`, `/deleting_page`, HTML-формы запуска/удаления и старые scan/cancel routes |
| `kinorium` | `/table/` и HTML/HTMX маршруты таблицы, поиска и загрузки CSV |
| `plex` | `/plex/<section>`, `/plex_section/` |
| `core` | `/preferences/`, `/login/`, `/logout/`, `/register/`, `/delete_account/`, `/tst/` |
| `tmdb_adapter` | HTML OAuth/auth page и callback маршруты старого adapter UI |
| `web_logger` | HTML/HTMX чтение и очистка логов |

Точные пути и методы брать из текущих `urls.py`: таблица выше задаёт охват по группам и не заменяет URL inventory в ходе реализации. Маршрут `frontend_fallback` — доставка Svelte SPA, а не Django UI; сохранить и проверить отдельно.

### 3. Удалить views, обслуживающие UI URLs

После удаления маршрутов удалить из `views.py` и `htmx_views.py` только функции и классы, которые обслуживали удалённые Django UI URLs. В частности, провести аудит:

- `core/views.py`, `core/auth.py`;
- `moviefilter/views.py`, `moviefilter/htmx_views.py`;
- `vault/views.py`;
- `kinozal_scan/views.py`, `kinozal_scan/htmx_views.py`, `kinozal_scan/deleting_since_date.py`;
- `kinorium/views.py`, `kinorium/htmx_views.py`;
- `plex/views.py`;
- `tmdb_adapter/views.py`, `tmdb_adapter/auth.py`;
- `web_logger/htmx_views.py`.

Файлы могут содержать смесь UI и прикладной логики. Удалять весь файл только после проверки оставшихся импортов и использования. Сохранять Ninja endpoint implementations и вызываемые ими сервисы, даже если они реализуют похожую операцию.

### 4. Составить отдельный список HTMX вызовов

До удаления HTMX handlers зафиксировать полный реестр: HTTP method + path + handler + возвращаемый HTML/фрагмент + вызываемая прикладная функция. Источник — `htmx` списки в URLConf, `hx-get`/`hx-post` в шаблонах и `request.htmx` в Python.

Предварительные группы по текущему дереву URL:

- RSS действия, таблица, торренты и счётчики: `moviefilter/urls.py`;
- Vault действия статуса/рейтинга/списков/TMDB: `vault/urls.py` и unprefixed patterns в корневом URLConf;
- запуск/отмена скана и удаление по дате: `kinozal_scan/urls.py`;
- таблица, поиск и загрузка Kinorium CSV: `kinorium/urls.py`;
- чтение/очистка логов: `web_logger/urls.py`.

HTMX endpoints считаются интерфейсными и удаляются вместе с UI routes. Их наличие не является основанием сохранять их как API. Если при разборе handler обнаружится полезная утилита или прикладная операция, которая используется вне старого UI, вынести/оставить её в подходящем service/API слое и удалить только HTML-обвязку.

### 5. Удалить остатки, нужные только старому UI

Когда templates, UI routes и связанные views удалены, повторно проверить импорты и usage и удалить только ставшие ненужными:

- forms, template tags, context processors и UI-only middleware;
- `django_htmx`, crispy forms и UI-only app/middleware registrations;
- шаблонные static assets и зависимости сборки старого интерфейса;
- redirects, reverse names и сообщения, относящиеся только к удалённым страницам.

Сохранять функции, которые используются парсером, Ninja API, admin, фоновыми задачами или другими backend-компонентами. В частности, не удалять по названию целые модули `services`, модели, migrations, management commands, Huey tasks, TMDB adapter инфраструктуру и websocket logging без подтверждения отсутствия backend usage.

## Аккуратность удаления

- Работать небольшими последовательными изменениями: templates, URLConf, views, UI-only helpers/dependencies.
- После каждого шага искать ссылки на удалённые template names, route names, view symbols и HTMX paths.
- Не менять модели, миграции и данные.
- Не чистить закомментированный или пользовательский код, если он не мешает удалению интерфейса.
- Удаление URL означает удаление старого Django UI endpoint; не требуется сохранять redirects для старых UI ссылок, если это не понадобится по отдельному решению.

## Проверка результата

- Поиск по репозиторию не находит оставшихся ссылок на удалённые templates, UI URL names и UI view symbols.
- Django загружается без ошибок import/URL/template configuration; `/admin/`, `/api/**`, SPA fallback и WebSocket работают.
- Запустить проектные backend/frontend проверки, не затрагивая данные локальной БД.
- Сверить итоговый список удалённых файлов и URL с отдельным HTMX inventory и убедиться, что в удалённых view-файлах не потеряны используемые backend utilities.

## Критерий завершения

В репозитории нет старых Django UI templates, UI URLs и обслуживающих их views/HTMX handlers; оставшиеся Django entrypoints обслуживают API, admin, SPA delivery и realtime/инфраструктуру, а общая прикладная логика остаётся доступной backend-компонентам.
