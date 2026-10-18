# Реестр legacy HTMX endpoints

Все перечисленные ниже маршруты принадлежали Django UI и удалены вместе с ним. Методы указаны по decorators/проверкам внутри handler; если явного ограничения нет — указано поведение существовавшего кода.

| URL | Метод | Handler | Ответ / побочный эффект |
|---|---|---|---|
| `/reset_rss/` | DELETE | `moviefilter.htmx_views.reset_rss` | Удаляет все `MovieRSS`, возвращает пустой 200; доступ ограничен login decorator. |
| `/ignore/<pk>` | POST | `moviefilter.htmx_views.ignore_movie` | Меняет priority на SKIP, удаляет cached image, пустой 200. |
| `/defer/<pk>` | POST | `moviefilter.htmx_views.defer` | Меняет priority на DEFER, пустой 200. |
| `/wait_trains/<pk>` | POST | `moviefilter.htmx_views.wait_trains` | Меняет priority на WAIT_TRANS, удаляет cached image, пустой 200. |
| `/get_rss_table_data/` | GET | `moviefilter.htmx_views.rss_table_data` | Возвращает `partials/rss-table.html`; фильтрует/пагинирует `MovieRSS`, готовит poster cache и Kinozal links. |
| `/kinozal_available_torrents/<kinozal_id>` | GET | `moviefilter.htmx_views.kinozal_download` | Ищет торренты в Kinozal и возвращает HTML fragment. |
| `/get_torrent_file/<kinozal_id>` | POST | `moviefilter.htmx_views.get_torrent_file` | Скачивает torrent, затем вызывает `KinozalDownloadImportService.enqueue_successful_download`; отвечает HTML glyph. Сервис/операцию не удалять, если используется API. |
| `/total_downloads/` | без ограничения метода | `moviefilter.htmx_views.total_downloads_for_movie` | Ищет варианты в Kinozal, возвращает HTML badge со счётчиком. |
| `/vault/htmx/toggle-status/` и `/htmx/toggle-status/` | POST | `vault.views.toggle_movie_status` | Меняет статус через `MovieStatusService`, возвращает HTML кнопки. |
| `/vault/htmx/rate-movie/` и `/htmx/rate-movie/` | POST | `vault.views.rate_movie` | Сохраняет оценку через `MovieStatusService`, возвращает HTML controls. |
| `/vault/htmx/remove-rating/` и `/htmx/remove-rating/` | POST | `vault.views.remove_rating` | Удаляет оценку через `MovieStatusService`, возвращает HTML controls. |
| `/vault/htmx/add-to-list/` и `/htmx/add-to-list/` | POST | `vault.views.add_to_list` | Добавляет запись списка, возвращает HTML alert. |
| `/vault/htmx/remove-from-list/` и `/htmx/remove-from-list/` | POST | `vault.views.remove_from_list` | Удаляет запись списка, возвращает пустой HTML. |
| `/vault/htmx/toggle-list-privacy/` и `/htmx/toggle-list-privacy/` | POST | `vault.views.toggle_list_privacy` | Меняет приватность списка, возвращает HTML badge. |
| `/vault/htmx/fetch-tmdb/` | POST | `vault.views.fetch_tmdb_data` | Запускает `TMDBMovieSyncService.sync_movie`, результат сериализует в HTML. |
| `/vault/htmx/fetch-tmdb-confirm/` | POST | `vault.views.fetch_tmdb_data_confirm` | Подтверждает TMDB кандидата через `TMDBMovieSyncService`, результат сериализует в HTML. |
| `/scan/` | GET | `kinozal_scan.htmx_views.scan` | Стартует `start_scan_task`, возвращает 202 и `X-Task-ID`; Ninja API имеет отдельный start endpoint. |
| `/cancel/<task_id>` | POST | `kinozal_scan.htmx_views.cancel_scan` | Сигнализирует отмену scan task, пустой 204; Ninja API имеет отдельный cancel endpoint. |
| `/kinorium_table_data/` | без ограничения метода | `kinorium.htmx_views.kinorium_table_data` | Возвращает HTML fragment таблицы Kinorium. |
| `/kinorium_search/<kinozal_id>` | GET | `kinorium.htmx_views.kinorium_search` | Строит URL поиска Kinorium и возвращает plain text. |
| `/table/` | GET/POST через `request.htmx` | `kinorium.views.table` | GET возвращает HTML страницы/фрагментов; POST принимает два CSV и заменяет содержимое Kinorium cache. |
| `/get_log/<log_type>` | без ограничения метода | `web_logger.htmx_views.get_log` | Возвращает текстовый лог; в новом UI есть Ninja endpoint. |
| `/clear_log/` | без ограничения метода | `web_logger.htmx_views.clear_log` | Очищает выбранный лог-файл; в новом UI есть Ninja DELETE endpoint. |

Примечание: таблица маршрутов в `vault/urls.py` была включена с префиксом `/vault/`, а часть тех же handlers была зарегистрирована повторно в `movie_filter_pro/urls.py` без префикса. Удалены обе регистрации.

Отдельный не-HTMX UI endpoint `/run_deleting_since_date` возвращал HTML для операции удаления старых записей; он также удален.

## Вызовы из старых templates

Реестр вызовов снят из удалённых templates в Git `HEAD` перед их удалением:

- `moviefilter/templates/rss.html` и `partials/rss-table.html`: GET таблицы/порции RSS; GET счётчика и вариантов торрента; POST действия defer, wait-trans и ignore.
- `moviefilter/templates/partials/kinozal_download.html`: POST скачивания выбранного torrent.
- `moviefilter/templates/partials/upload_kinorium_form.html`: multipart POST на `/table/` для загрузки двух CSV.
- `moviefilter/templates/upload_csv.html`: multipart POST по текущему URL, но соответствующего подключенного route/view в URLConf не найдено.
- `vault/templates/vault/movie_detail.html`, `movie_list.html`, `list_detail.html`: явные POST вызовы относятся к TMDB sync, статусу, оценке и удалению оценки. Add/remove list и privacy handlers зарегистрированы, но явных HTMX вызовов в templates не найдено.
- `kinorium/templates/kinorium-table.html`: GET для HTML страницы/фрагментов и GET данных таблицы.
- `kinozal_scan/templates/scan_page.html`: GET старт скана; JS динамически задаёт POST на `/cancel/<task_id>`; GET чтение/очистка логов.
- `kinozal_scan/templates/deleting.html`: POST `/run_deleting_since_date`; также есть вызов `/delete_all`, для которого route/view в URLConf не найдено.
- `core/templates/preferences_update_form.html`: DELETE `/reset_rss/`.
- `tmdb_adapter/templates/tmdb_auth.html`: GET старта старого TMDB auth flow. Approve вызывается обычной HTML-ссылкой из ответа handler; вариант кнопки с `hx-get` оставлен только в комментарии.

`request.htmx` дополнительно использовался в `core.views.tst` и `kinorium.views.table`; это проверки/ветвления внутри удалённых Django views, а не отдельные URL.
