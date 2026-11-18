# План: освежение карточки AI Predict через TMDB (для ленты Kinozal)

Статус: **отложено на будущее**. Сейчас AI Predict в Kinozal считает по карточке,
собранной из полей `MovieRSS` (`ai_predict/services/movie_card.py::build_rss_movie_card`).

## Зачем

Сделать вход AI Predict для раздач Kinozal ближе к тому, что получает Vault, чтобы
оценка не зависела от источника строки: одинаковые жанры, страны, тип, длительность,
язык, рейтинг TMDB и описание вместо «сырых» текстовых полей раздачи
(`genres = "Драма, Триллер"` и т.п.).

Полного равенства без импорта в Vault не будет: OMDB-рейтинги/голоса, роли персон из
локальной БД, ключевые слова и коллекции появляются только после полного TMDB-sync.
Остаточная разница на оценку влияет слабо.

## Источники данных (порядок приоритета)

1. **Vault** — если фильм уже есть в Vault (совпадение по `imdb_id` / `kinopoisk_id`,
   либо связь через `VaultConnectionEvent.movie_rss`) и у него заполнен `tmdb_id`:
   использовать существующий `build_movie_card(movie)`. Сеть не нужна, карточка
   буквально совпадает с Vault.
2. **TMDB (read-only)** — резолв TMDB id и сборка карточки из live-данных TMDB,
   без импорта в Vault.
3. **Kinozal** — текущая карточка из `MovieRSS` как безусловный фолбэк.

## Технически

### 1. Новый сервис `ai_predict/services/tmdb_card.py`

- Резолв TMDB id:
  - `TMDBMovieMatchingService.find_by_imdb_id(movie_rss.imdb_id)`, если `imdb_id` есть
    (он заполняется с детальной страницы трекера и есть у большинства раздач);
  - иначе `TMDBMovieMatchingService.match_movie(probe)` по `title` / `original_title` /
    `year`, но **только** при `auto_match`.
- Загрузка деталей: `get_tmdb_client()` + `tmdb.movie(id)` / `tmdb.tv_show(id)` + credits
  (1–2 запроса, language=RU — как в Vault).
- Сборка карточки в той же схеме, что `build_movie_card`:
  `title, original_title, year, type, runtime_min, genres, countries, language,
  ratings{tmdb}, directors, cast, description, age_years` (+ `seasons`/`episodes` для
  сериалов); дополнительно смержить из самой раздачи `imdb`/`kinopoisk` рейтинги и
  `translation`.

### 2. `prediction_service.predict_rss_movie`

Реализует порядок источников Vault → TMDB → Kinozal. В `input_snapshot` писать
`card_source` (`vault` | `tmdb` | `kinozal`) и `tmdb_id` (для tmdb), чтобы в истории
было видно, на каких данных считали.

### 3. Кэш (без миграций)

`django.core.cache` (прецедент — `vault/services/person_images_service.py`):

- `ai_predict:rss_tmdb:{rss_movie_id}` → `(tmdb_id, media_type)`, TTL ~30 дней;
- `ai_predict:tmdb_card:{media_type}:{tmdb_id}` → готовая карточка, TTL ~7 дней.

Если позже понадобится показывать `tmdb_id` прямо в ленте — можно добавить nullable
поля в `MovieRSS`, но для этой задачи не требуется.

### 4. Фолбэк

Нет ключа TMDB / таймаут / `not_found` / `needs_user_choice` → молча считаем по
карточке Kinozal. Предсказание не должно падать из-за TMDB.

### 5. UI

`front/src/lib/components/ai-predict/AiPredictDialog.svelte`: бейдж источника данных
(«Vault», «TMDB», «Kinozal»). Источник резолвить при открытии диалога (показать, что
подтянулось), а не в момент «Запустить анализ», иначе ожидания складываются.

## Стоимость

Первый прогон по строке — +1–2 запроса TMDB (~0.3–1 с на фоне ~10 с LLM), дальше из
кэша.

## Риски

- **Неверный матч** — главный риск fallback-матчинга по названию/году: модель оценит
  не тот фильм. Политика: `auto_match` берём, `needs_user_choice` — не угадываем.
  С `imdb_id` риск минимален.
- **Доступность TMDB** — деградация к карточке Kinozal, без ошибок для пользователя.
- **Скорость** — синхронный predict; поэтому резолв при открытии диалога, а не при
  запуске.
- **Дублирование логики** — если live-карточка понадобится вне AI Predict, вынести
  сервис в `vault/services/`.

## Альтернатива без сети

Расширить `build_rss_movie_card` нормализацией (год, списки) и оставить Kinozal
единственным источником. Плюс: детерминированно и быстро. Минус: разница в жанрах,
описании, отсутствие рантайма/языка/TMDB-рейтинга сохраняется.

## Решения по умолчанию (предложение)

1. Всегда пробовать TMDB с фолбэком + бейдж источника (без тумблера).
2. Неоднозначный матч — тихий фолбэк на Kinozal (выбор кандидата — отдельный этап).
3. Кэш в `django.core.cache`, без миграций.

## Объём работ

Новый сервис (~150–200 строк) + правка `predict_rss_movie` + бейдж в диалоге + тесты
(резолв по `imdb_id`, fallback, кэш, ошибка TMDB). Миграций нет.
