# PLANS_BESTFILMOF_INTEGRATION.md — интеграция bestfilmsof.com

Персистивная память по задаче. Обновлять по мере продвижения.

## Статус

- [x] Создан Django app `bestfilmsof` и подключён (`INSTALLED_APPS`, `/api/bestfilmsof/`, Huey tasks).
- [x] Перенесён прототип из `bestfilmsof/example_code` в MVP-виде.
- [x] Бэкенд: модели, сервисный слой, Ninja API, фоновые задачи, тесты (28 тестов).
- [x] Frontend: пункт меню **BestMovies** и страница `/best-movies` (Svelte 5 + shadcn-svelte).
- [x] Фильтр по статусам Vault: все / непросмотренные / «буду смотреть» + счётчики.
- [x] URL-состояние: год, жанр, веса, статус, сортировка, страница; back/forward и ссылки.
- [x] Клиентская сортировка, infinite scroll по 50 строк и sticky header таблицы.
- [x] Переключатель вида «обложки ↔ список» с иконкой; сетка использует VaultImage и MovieStatusBadges.
- [x] Проверено вживую: синк `2010/western`, RU-backfill из TMDB, чтение с приоритетом коллекции Vault.
- [ ] Дизайн/вёрстка под общий стиль (следующий этап).
- [ ] Интеграция со статусами Vault: действия записи (просмотрено/буду смотреть/рейтинг) (следующий этап).
- [x] Infinite scroll / постраничная догрузка: рендер порциями по 50 строк.

## Что это

Источник «лучших фильмов»: `https://bestfilmsof.com/`.
API отдаёт готовый рейтинг по году/жанру. Веса («Weigh the score your way»)
можно пересчитывать локально по формуле прототипа.

Оригинальный прототип лежит в `bestfilmsof/example_code/` — **не удалять**,
он остаётся эталоном и источником README/PLAN.

## Границы парсинга (важно)

**Сайт целиком не парсится и не зеркалируется.** Нет обхода всех годов/жанров,
нет периодических задач и предзагрузки «всего сайта». «Синк» в этом документе
означает загрузку **только того набора, который выбрал пользователь**:

- выбрал год + жанр → тянется список ровно этой пары (все её страницы,
  например 2010/drama = 282 фильма = 6 запросов по 50);
- выбрал только жанр → один запрос `/api/movies/genre/{genre}` для сводки
  этого жанра;
- остальные пары не трогаются, пока пользователь сам их не откроет.

Локально сохраняются только слепки тех пар/сводок, которые уже запрашивались
(это поведение самого прототипа: snapshot + TTL + Refresh). Если захочется
вообще без локального кеша — это отдельное решение, см. «Следующие шаги».

## Принятые решения (важно)

1. **Синк — в Huey, не в HTTP-запросе.** Первый холодный синк пары год+жанр
   занимает десятки секунд; API только атомарно занимает синк и отдаёт статус.
   Frontend опрашивает `state == "syncing"` каждые 2.5 с.
2. **Сингл-флайт через `BestfilmsSync` + `run_token`.** `claim()` ставит
   `running`, задача сверяет токен; повторный/просроченный запуск безопасно
   скипается. Через 30 минут «зависший» running можно перезанять.
3. **Ключ синка — строка, а не NULL-пара.** `key = "list:{year}:{genre}"` /
   `"summary:{genre}"`. Это убирает проблему Postgres, где `UNIQUE(year, genre)`
   не защищает от дублей при `year IS NULL`.
4. **Кеш метаданных — из бесплатного `metadata` bestfilmsof.**
   В ответе уже есть TMDB `id`, `title`, `overview`, `poster_path`,
   `release_date`. Отдельные EN-запросы к TMDB не нужны.
5. **Русский язык: коллекция Vault -> TMDB RU -> английский fallback.**
   - При чтении приоритет: `vault.Movie` (title/description/poster) ->
     `BestfilmsCache` -> значения `BestfilmsEntry`.
   - Фоновая задача `bestfilmsof_backfill_metadata` добирает `title_ru`/
     `overview_ru` из TMDB (клиент из Preferences, `language="ru-RU"`).
   - Фильмы, которые уже есть в коллекции, не дёргают TMDB: русские данные
     берутся из Vault без записи в кеш.
6. **TMDB — только через Preferences** (`tmdb_adapter.client_singleton`),
   без `TMDB_ACCESS_TOKEN` из `.env` (как в прототипе). `tmdbfusion` не
   добавляем: в проекте уже есть `tmdbapis`/`tmdb_adapter`.
7. **Полный слепок выбранной пары, без постраничного on-demand.** Пока загрузка
   пары не завершена, entries не создаются (bulk-вставка в конце), поэтому веса
   никогда не считаются по неполному списку. Это не «весь сайт»: грузится только
   выбранный год+жанр. Догрузка чанками — будущий этап.
8. **Связь с Vault — только логическая, по `tmdb_id`.** FK нет. Синк
   bestfilmsof пишет только свои таблицы.
9. **Статусы Vault читаются, но не меняются.** `status_service` одним запросом
   достаёт `UserMovie` для всех tmdb_id пары и считает три режима:
   `all`, `unwatched` (всё, кроме `WATCHED`), `will_watch` (`PLAN`). Фильмы без
   `UserMovie` считаются непросмотренными. Экшены записи статусов — следующий этап.

## Файлы

```
bestfilmsof/
  constants.py                  # URL, лимиты, жанры, пресеты весов
  client.py                     # HTTP-клиент bestfilmsof.com
  parsing.py                    # raw JSON -> dict моделей
  scoring.py                    # формула локального пересчёта весов
  models.py                     # BestfilmsEntry/Cache/Sync/GenreYear
  api.py                        # Ninja API (/api/bestfilmsof/)
  tasks.py                      # Huey: sync + RU backfill
  admin.py                      # отладка в Django Admin
  management/commands/sync_bestfilms.py  # ручной синк без Huey
  services/
    collection_service.py       # чтение метаданных из vault.Movie
    metadata_service.py         # RU backfill из TMDB
    read_service.py             # списки/сводки из своей БД
    status_service.py           # статусы Vault + счётчики по режимам
    sync_service.py             # claim/run + дифф слепка + TTL
  tests/                        # 28 тестов (scoring, sync, read, api)
  example_code/                 # исходный прототип (эталон, не трогать)
front/src/routes/best-movies/   # страница BestMovies
front/src/lib/bestfilmsof.ts    # типы и подписи
front/src/lib/template-data.ts  # пункт меню "BestMovies"
movie_filter_pro/urls.py        # /api/bestfilmsof/
movie_filter_pro/huey.py        # импорт bestfilmsof.tasks
```

## Модели

- `BestfilmsEntry` — слепок рейтинга `(year, genre, imdb_id)`, позиция, скор,
  рейтинги/касса/награды, компоненты скора для локального пересчёта.
  `genre=""` = весь год.
- `BestfilmsCache` — TMDB-метаданные (PK `tmdb_id`), EN + RU.
- `BestfilmsSync` — состояние синка: `key`, `status`, `run_token`,
  `synced_at`, `started_at/finished_at`, `error_message`, `last_stats`.
- `BestfilmsGenreYear` — сводка жанра по годам (count + топ-фильм).

Миграция: `bestfilmsof/migrations/0001_initial.py` (применена на dev).

## API

Все endpoint-ы требуют авторизации (Django session).

- `GET /api/bestfilmsof/filters` — годы, жанры, пресеты, `year_min/year_max`.
- `GET /api/bestfilmsof/movies?year=&genre=&page=&limit=&preset=&status_filter=&w_*=` —
  список; при необходимости ставит синк в очередь; `state`:
  `idle | queued | syncing | ready | error`.
  `status_filter`: `all | unwatched | will_watch`; в ответе есть `counts`
  (`all/unwatched/will_watch`) и поля статуса каждого фильма
  (`watch_status`, `in_favorites`, `rating`).
- `POST /api/bestfilmsof/movies/refresh?year=&genre=` — принудительный синк.
- `GET /api/bestfilmsof/genres/{genre}` — сводка по годам.
- `POST /api/bestfilmsof/genres/{genre}/refresh` — принудительный синк сводки.
- `GET /api/bestfilmsof/sync-state?year=&genre=` — статус без запуска.

`preset`: `default | critics | crowd | awards | no-boxoffice | custom`.
Для `custom` веса передаются как `w_imdb`, `w_critics`, `w_awards`,
`w_boxoffice` (0..100, сумма > 0, иначе fallback на default).

## URL-состояние страницы

Страница `/best-movies` хранит в query params:

- `year`, `genre` — выбор пары (год может отсутствовать — режим сводки);
- `preset`, `w_imdb/w_critics/w_awards/w_boxoffice` — веса (последние 4 —
  только для `preset=custom`);
- `status` — `all | unwatched | will_watch`;
- `sort`, `dir` — сортировка и направление;
- `page` — сколько страниц по 50 строк уже показано (infinite scroll).

Синхронизация сделана без shallow `pushState` для фильтров: в SvelteKit 2
`pushState`/`replaceState` не обновляют `page.url`, а при возврате назад `load`
получает URL, сохранённый в history, а не тот, что виден в адресной строке
(issues #13569/#11465). Поэтому:

- смена года/жанра/весов/статуса/сортировки — обычная навигация `goto(...)`:
  URL, `page.url` и history остаются согласованными;
- `afterNavigate` + `popstate` читают `window.location` и восстанавливают
  состояние при back/forward;
- прогресс infinite scroll (`page`) обновляется через `replaceState` — без
  навигации и без повторной загрузки данных.

Таблица вынесена из внутреннего скролл-контейнера: скролл **системный**, как в
Vault. Заголовок `sticky top-14` (под шапкой приложения), sentinel для
IntersectionObserver находится в потоке страницы. Колонки скрываются адаптивно
(`sm/lg/xl`), таблица `table-fixed`, поэтому горизонтального скролла нет.

Вид страницы переключается одной кнопкой (иконка `LayoutGrid`/
`TextAlignJustify`): сетка обложек или таблица-список. Сетка использует
`VaultImage` и стандартный `MovieStatusBadges` (статусы, оценка, год, избранное),
поэтому выглядит как карточки Vault. Выбранный вид пока не пишется в URL —
это локальное состояние страницы.

Сортировка и пагинация — клиентские поверх загруженных до 500 строк; фильтр по
статусам — серверный (чтобы `total` и `counts` были корректны для всего списка).

Важно: API по-прежнему отдаёт до 500 строк одним запросом. Это осознанно:
корректная сортировка и пересчёт весов требуют весь список пары. Infinite scroll
здесь — на уровне рендера/DOM, а не сетевой постраничный. Если понадобится
сетевой вариант, сортировку и веса нужно переносить на бэкенд.

## TTL (из прототипа)

- текущий год — 24 часа;
- прошлый год — 7 дней, после 1 апреля — 30 дней;
- архив — 90 дней;
- жанровые сводки (`year=None`) — 24 часа;
- ни разу не синкалось — всегда устарело.

## Запуск и проверки

```bash
# миграции
uv run python manage.py migrate bestfilmsof

# Huey-воркер обязателен для фонового синка
uv run python -m huey.bin.huey_consumer movie_filter_pro.huey.HUEY -k thread -w 2 -v -S

# ручной синк без Huey (диагностика / прогрев)
uv run python manage.py sync_bestfilms 2010 --genre drama
uv run python manage.py sync_bestfilms --genre drama
uv run python manage.py sync_bestfilms 2010 --genre drama --force

# тесты
uv run python manage.py test bestfilmsof

# frontend
cd front && pnpm run check && pnpm run build
```

Если Huey не запущен, страница покажет «Синхронизация», но данные не придут.
Через 30 минут claim можно перезанять; для ручной проверки удобно вызывать
`SyncService.claim()` + `SyncService.run_claimed()` из `manage.py shell`.

### Если статус «В очереди» не меняется

Признак: в БД `BestfilmsSync.status="running"`, но `worker_started_at IS NULL`,
очередь Huey пуста. Это значит, что задача ушла воркеру, но он её не узнал
(обычно воркер запущен **до** появления `bestfilmsof.tasks`).

Что делает код:
- задача, которую воркер реально начал, ставит `worker_started_at`;
- если `worker_started_at` пуст и с постановки прошло >60 с, следующий `claim`
  считает задачу потерянной, меняет `run_token` и ставит новую;
- старые задачи с прежним токеном безопасно скипаются;
- кнопка «Обновить данные» (`force`) перезапускает такую задачу сразу.

Что нужно сделать пользователю: **перезапустить Huey-воркер** (он читает
`movie_filter_pro/huey.py` при старте) и backend (Django не перезагружает
Python-код сам), затем открыть страницу заново или нажать «Обновить данные».
После рестарта воркера новые задачи подхватятся.

## Проверено вживую (dev)

- `2010/western`: 2 фильма, 1 запрос к bestfilmsof, `cache_created=2`.
- `--genre western` (сводка): 73 года, 72 новых кеша-строки, 1 запрос, 1.33 с.
- `True Grit` найден в Vault → русское название/описание из коллекции,
  `in_collection=true`.
- RU-backfill: `requested=2, fetched=1, skipped_collection=1, errors=[]`
  (`Red Hill` → «Красный холм»).
- `manage.py test bestfilmsof` — 28 OK.
- `pnpm run check` — 0 ошибок (только старые warnings проекта).
- `pnpm run build` — успешно.

## Ловушки bestfilmsof API (из прототипа)

- `limit` максимум 50 (51+ → HTTP 400).
- Год минимум 1874; меньше → HTTP 400.
- `/api/movies` **без** `year` молча подставляет текущий год — так вызывать нельзя.
- Без `genre` — весь год (можно).
- Origin сериализует конкурентные запросы; страницы тянем последовательно.
- В `metadata` нет бюджета, только `gross`.

## UX backlog (часть уже сделана)

Быстрые победы:
- [x] состояние фильтров/сортировки/страницы в URL query params (back/forward, ссылка на подборку);
- [ ] запоминать последний выбранный год/жанр/веса в localStorage (URL уже сохраняет состояние; localStorage — для возврата без query);
- [x] infinite scroll вместо таблицы на 500 строк (по 50 строк с догрузкой при скролле);
- сохранять предыдущие строки при перезагрузке фильтра и показывать skeleton/overlay, а не пустой экран;
- [x] sticky header таблицы (внутри скролл-контейнера); компактный режим — ещё нет;
- «Скрыть неинтересные» (`wont_watch`) отдельным переключателем.

Фильтры:
- только в коллекции / только не в коллекции;
- диапазоны IMDb/RT/Meta/скора bestfilmsof и минимальное число голосов;
- награды: Oscar win/nominee, Best Picture;
- касса: есть/диапазон;
- избранное Vault, мои списки, мой рейтинг;
- провайдеры просмотра (в ответе bestfilmsof есть `watch`, сейчас не храним);
- исключить фильмы без постера/описания.

Сортировки:
- IMDb, голоса, RT, Meta, касса, award_points, дата выхода, название;
- мой рейтинг Vault и разница «мой рейтинг − скор сайта»;
- «удиви меня» (random).

Сценарии:
- быстрые действия в строке: «Буду смотреть», «Просмотрено», избранное, оценка 1–10 (оптимистичный UI);
- «Добавить в Vault» для фильмов не из коллекции (через существующий TMDB import flow);
- hover-превью постера, клик по фильму → Vault detail;
- объяснение скора: раскрыть компоненты IMDb/критики/награды/касса;
- сохранённые пресеты подборок («вечер: 2010-е, триллер, IMDb 7+, не просмотрено»);
- экспорт CSV и «поделиться ссылкой».

## Следующие шаги

1. **Статусы Vault**: фильтр по статусам и поля `watch_status`/`rating`/
   `in_favorites` уже есть; остались экшены «просмотрено/буду смотреть/рейтинг»
   через `vault.services.movie_status_service` с оптимистичным UI.
2. **Дизайн**: карточки фильмов вместо тяжёлой таблицы, постеры через
   `VaultImage`, адаптив, скелетоны, нормальные пустые состояния.
3. **Infinite scroll**: рендер порциями по 50 строк уже есть. Сетевой
   постраничный вариант (если понадобится) требует переноса сортировки/весов
   на бэкенд — это отдельный архитектурный шаг.
4. **Коллекция как источник**: при добавлении фильма из BestMovies в Vault
   использовать существующий TMDB import flow, чтобы кеш не дублировал данные.
5. **Observability**: вывести `last_stats` (время, запросы, ошибки TMDB) в
   UI-панель диагностики.
6. **Тесты**: добавить тест на повторный claim после таймаута, на ошибку
   сети (частичный прогресс не сохраняется), на RU-backfill с моками.
7. **Опционально: режим без кеша.** Если локальное сохранение не нужно,
   `GET /movies` может тянуть выбранную пару live (медленно: десятки секунд)
   и не писать `BestfilmsEntry/Cache`; веса всё равно требуют полного списка
   пары. Решение ещё не принято.

## Правила, которые нельзя нарушать

- Синк bestfilmsof **никогда** не пишет в таблицы Vault.
- Сервисный слой bestfilmsof не импортирует views/urls.
- API-ключи/URL сервисов — только Preferences, не `.env`.
- Все файлы — LF.
- Не удалять `example_code` без явного запроса.
