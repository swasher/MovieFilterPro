# План qBittorrent-интеграции — итоговая версия

## Принятые решения

- qBittorrent: **5.1.4+**, без fallback под старые версии.
- Архитектура: отдельный Django app **`qbittorrent`** — модели, сервисы, API.
- В модели раздачи **не храним** `movie_rss` и `kinozal_id`: для связи с Vault достаточно FK на Movie, а Kinozal ID используется только в запросе и логах.
- Архив `.torrent`: поле в **Preferences**, Docker-share `/app/backup_torrents`.
- Один фильм может иметь **несколько** раздач. Сигнализацию о второй раздаче делаем позже.
- Удаление после просмотра: **qbt-торрент + медиафайлы + архив `.torrent` + локальная запись**. Это этап 3.
- Live-прогресс в первой фазе **не делаем**: страница qbt обновляется кнопкой/F5.
- Ссылку в qbt UI с фильтром по infohash **откладываем**: штатный WebUI не умеет фильтровать по hash.
- Первая фаза: backend link + Preferences + минимальная таблица раздач.

---

## 1. Модель данных (`qbittorrent/models.py`)

### `Torrent`

| Поле | Назначение |
|---|---|
| `movie` | FK на `vault.Movie`, nullable, `SET_NULL` |
| `info_hash` | ID раздачи в qBittorrent, unique |
| `name` | Название раздачи |
| `source_url` | Страница раздачи Kinozal |
| `torrent_file` | Относительный путь к `.torrent` в backup-папке |
| `save_path` | Путь qBittorrent |
| `content_path` | Путь к файлу/папке в qBittorrent |
| `last_error` | Ошибка архивного слоя/сверки |
| `created_at`, `updated_at` | Даты |

`movie` nullable, потому что фоновый TMDB-импорт может не найти фильм. `info_hash` unique защищает от дублей.

### `TorrentEvent`

Персистентный журнал: добавление, ошибка добавления, сохранение архива, привязка к Movie, удаление.

Поля: `torrent`, `movie`, `level`, `event_type`, `message`, `payload`, `created_at`.

---

## 2. Preferences

В `UserPreferences`:

- `qbt_url`;
- `qbt_username`;
- `qbt_password`;
- `torrents_backup_folder`.

Старый `torrents_hotfolder` больше не используется в download-flow и убран из Preferences UI/API. Колонка в БД оставлена deprecated, чтобы не делать разрушительную миграцию.

В UI — карточка **qBittorrent**:

- API URL;
- логин;
- пароль;
- папка backup `.torrent`;
- кнопка «Проверить подключение»;
- resolved path и exists on backend;
- подсказка: в Docker URL — имя сервиса, не `localhost`.

---

## 3. Download flow

1. Пользователь жмёт Download в Kinozal.
2. Backend скачивает `.torrent` в память.
3. `bencodepy` извлекает v1 infohash, имя и comment.
4. `qbittorrent-api` добавляет торрент байтами:
   `torrents_add(torrent_files=bytes, tags=..., is_sequential_download=True)`.
5. Проверяем, что раздача реально появилась через `torrents_info`.
6. Сохраняем `.torrent` в backup-папку как `<info_hash>.torrent`.
7. Создаём/переиспользуем `Torrent`.
8. Ставим существующий HUEY-импорт в Vault, передавая `qbt_torrent_id`.
9. После успешного импорта и выставления «Буду смотреть» — привязываем `Torrent.movie`.
10. Возвращаем frontend `info_hash`, имя, путь архива.

Если архив не сохранился, но qbt добавил раздачу — привязка создаётся с предупреждением; архив можно добрать через `torrents_export`.

Если qbt не подтвердил добавление — ошибка, запись не создаётся.

---

## 4. API

Новый префикс `/api/qbittorrent/`:

- `GET /status` — настроен ли qbt, доступен ли, версия, количество раздач;
- `POST /test` — проверка сохранённых или переданных настроек;
- `GET /torrents?limit=&offset=` — список раздач qbt + локальная привязка к Vault;
- `POST /progress` — batch-прогресс по infohash;
- `POST /torrents/{info_hash}/link` — ручная привязка;
- `POST /torrents/{info_hash}/delete` — удаление раздачи, файлов, архива и локальной записи;
- `POST /movies/{movie_id}/torrents/delete` — удаление всех раздач фильма.

В `vault/api.py`:

- `MovieOut.torrent_linked`;
- фильтр `has_torrent=true|false`.

`torrent_linked` считается по локальной таблице, без запроса в qbt. Список Vault не должен зависеть от доступности qBittorrent.

---

## 5. Frontend

### Preferences

Новая карточка qBittorrent, тест подключения, backup-папка. Старый hotfolder UI удалён.

### `/qbittorrent`

Минимальная таблица:

- имя раздачи;
- состояние;
- прогресс;
- размер;
- скорость;
- ETA;
- привязанный фильм Vault.

Обновление — кнопка «Обновить» или F5. Без polling и WebSocket в первой фазе.

### Kinozal

Download теперь вызывает qbt API. Ошибки qbt показываются в диалоге и ведут в Preferences.

---

## 6. Этапы

### Этап 1 — сейчас

- [x] `qbittorrent-api` + `bencode.py`
- [x] app `qbittorrent`
- [x] модели `Torrent`, `TorrentEvent`
- [x] сервисы qbt client / archive / add / list / link
- [x] Preferences backend + UI
- [x] новый Download flow через qbt API
- [x] привязка после Vault-импорта
- [x] `torrent_linked` + `has_torrent`
- [x] `/api/qbittorrent/*`
- [x] страница `/qbittorrent`
- [x] тесты backend
- [x] `pnpm check`

### Этап 2 — Vault UI

- [x] иконки `link-2` / `link-2-off` на карточках «Буду смотреть»;
- [x] фильтр «Только без раздачи qBittorrent»;
- [x] проценты загрузки на карточках и в list view (polling 5с);
- [x] ручная привязка раздачи к фильму;
- [x] ссылка на страницу Kinozal и путь qbt в detail;
- [ ] ссылка в qbt UI по infohash — отложена (штатный WebUI не фильтрует по hash).

### Этап 3 — удаление и «Просмотрено»

- [x] модалка при установке WATCHED (показывается, если у фильма есть привязанные раздачи);
- [x] отдельная кнопка «Удалить раздачу» в блоке qBittorrent на странице фильма;
- [x] удаление qbt-торрента с файлами (`torrents_delete(delete_files=True)`);
- [x] удаление архива `.torrent` из backup-папки;
- [x] удаление локальной записи `Torrent`;
- [x] персистентный журнал `torrent_deleted` / `torrent_delete_failed`;
- [x] `POST /api/qbittorrent/torrents/{info_hash}/delete`;
- [x] `POST /api/qbittorrent/movies/{movie_id}/torrents/delete`;
- [x] `toggle-status` принимает `delete_torrents` и возвращает `torrents_deleted` + `torrent_delete_errors`.

Если qBittorrent недоступен, локальная запись и архив сохраняются, чтобы удаление можно было повторить.
Статус WATCHED при этом всё равно выставляется, а frontend показывает предупреждение.

### Этап 4 — WebSocket

- `/ws/qbt/`;
- poller в web-процессе;
- live-прогресс.

### Этап 5 — полноценный qbt UI

- добавление `.torrent` через MFP;
- автоимпорт в Vault;
- фильтры/сортировка;
- ручное связывание.

---

## 7. Хрупкие места и меры

- `torrents_add` может вернуть успех, но не создать раздачу — проверяем `torrents_info`.
- Дубликат раздачи — `Conflict409Error`, переиспользуем существующую запись.
- `Content-Disposition` не используется для пути архива — имя строится по infohash.
- Архив не является watch-папкой qbt.
- `content_path` — путь внутри контейнера qbt, не обязательно доступен MFP/Plex.
- Ссылка на Kinozal: comment из `.torrent`, иначе конструируется из активного зеркала.
- Пароль qbt хранится в БД plaintext, как остальные сервисные ключи проекта.
- При удалении после просмотра удаляется всё, включая disaster-копию `.torrent`.

---

## 8. Проверка

```bash
uv run python manage.py test qbittorrent vault core moviefilter
cd front && pnpm check
```

Плюс ручная проверка с qBittorrent 5.1.4: test connection, Download, список раздач, привязка к Vault.
