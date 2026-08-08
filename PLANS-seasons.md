# План: Добавление поддержки сезонов и эпизодов для сериалов

## Текущее состояние (анализ)

### ✅ Уже реализовано в БД (модели + миграции)
- **Модели** в `vault/models.py`:
  - `Season` (строки 269-290): season_number, title, description, note, release_date, poster, source
  - `Episode` (строки 292-303): episode_number, title, description, duration, release_date
  - Связи: `Movie.seasons` (related_name), `Season.episodes` (related_name)
  - Уникальные индексы: `(movie, season_number)` и `(season, episode_number)`

- **Поля в Movie** (строки 176-178):
  - `seasons_count` - количество сезонов
  - `episodes_count` - количество эпизодов
  - `is_ongoing` / `year_end` - для отслеживания статуса

- **TMDB Sync** (`vault/services/tmdb_movie_sync.py`):
  - `_apply_tv_payload()` (строки 214-243) заполняет `seasons_count` и `episodes_count` из TMDB
  - Статусы мапятся правильно для TV (`_map_tmdb_status` строки 661-670)

### ❌ Что НЕ реализовано

| Компонент | Статус |
|-----------|--------|
| **Модель `UserSeason`** | Не создана (нужна для UI) |
| **API эндпоинты** для сезонов/статусов | Отсутствуют |
| **TMDB sync деталей сезонов/эпизодов** | Отсутствует (sync загружает только счетчики) |
| **Синхронизация статусов сезонов** при TMDB sync | Не реализована |
| **Frontend** (блок сезонов на карточке сериала) | Нет отображения сезонов |
| **clear_vault_data** — очистка UserSeason | UserSeason еще не существует |

---

## План имплементации

### Этап 1: API слой (Backend) — Приоритет: ВЫСОКИЙ

#### 1.1 Добавить схемы в `vault/api.py`
```python
class SeasonOut(Schema):
    id: int
    season_number: int
    title: str
    description: str
    release_date: str | None
    poster_url: str | None
    episodes_count: int

class EpisodeOut(Schema):
    id: int
    episode_number: int
    title: str
    description: str
    duration: int | None
    release_date: str | None

class SeasonDetailOut(SeasonOut):
    episodes: list[EpisodeOut]
```

#### 1.2 Добавить эндпоинты в `vault/api.py`
```
GET  /api/vault/movies/{slug}/seasons          → list[SeasonOut]
GET  /api/vault/movies/{slug}/seasons/{num}    → SeasonDetailOut
GET  /api/vault/seasons/{id}/episodes          → list[EpisodeOut]
```

#### 1.3 Расширить `MovieDetailOut`
Добавить поле `seasons: list[SeasonOut]` (или `seasons_count` + флаг `has_seasons_detail`)

---

### Этап 2: TMDB Sync — Добавление деталей сезонов/эпизодов

#### 2.1 В `TMDBMovieSyncService._apply_tv_payload()`
После сохранения счетчиков добавить вызов `_sync_seasons_and_episodes(movie, details, tmdb)`

#### 2.2 Новый метод `_sync_seasons_and_episodes`
- Загрузить детали сезонов через `tmdb.tv_show_seasons(tmdb_id)` или используя `details.seasons`
- Для каждого сезона:
  - Создать/обновить `Season` (season_number, title, description, release_date, poster)
  - Загрузить эпизоды сезона через `tmdb.tv_show_season(tmdb_id, season_number)`
  - Создать/обновить `Episode` (episode_number, title, description, duration, release_date)

#### 2.3 Важно: Использовать `tmdb_adapter.client_singleton.get_tmdb_client()`

---

### Этап 3: Frontend (Svelte 5 + shadcn-svelte) — Приоритет: ВЫСОКИЙ

#### 3.1 Страница сериала `front/src/routes/(vault)/movies/[slug]/+page.svelte`
- Добавить секцию "Сезоны" (после "Съемочная группа" или в раскрывающемся блоке)
- **Без отдельных страниц** для сезонов/эпизодов
- Использовать `Accordion` из shadcn-svelte (один AccordionItem на сезон)
- В заголовке сезона: номер, название, год выхода, количество эпизодов
- Внутри аккордеона (по клику): список эпизодов (номер, название, дата) — опционально, можно скрыть за вторым уровнем
- **На каждом сезоне (в заголовке аккордеона):**
  - Toggle "Просмотрено" (checkbox или иконка галочки)
  - StarRating (оценка 1-10)
  - Сохранение через `PATCH /api/vault/seasons/{id}/status`

#### 3.2 Data fetching
- В `+page.ts` (load) подгружать сезоны параллельно с фильмом для сериалов
- `SeasonOut` включает `episodes_count`, `user_state` (watch_status, rating)

#### 3.3 UI компоненты
- Использовать существующие: `StarRating`, `Checkbox`/`Switch` из shadcn-svelte
- Кастомный `SeasonAccordionItem` — обертка над AccordionItem

---

### Этап 4: Синхронизация статусов сезонов при TMDB Sync — Приоритет: ВЫСОКИЙ

**Проблема:** При импорте из Kinorium CSV сезоны не создаются (CSV не содержит этих данных). Сезоны создаются только при TMDB sync.

**Решение:** В момент TMDB sync (когда сериал получает сезоны из TMDB) — проставить статусы сезонов на основе пользовательского статуса самого сериала (`UserMovie`):
- Если у сериала `watch_status == WATCHED` → все сезоны получают статус "просмотрен"
- Если `watch_status == PLAN` или `SKIP` или пусто → все сезоны получают статус "не просмотрен" (или "планирую")

**Требуется новая модель** `UserSeason` (см. Этап 5, переносим в обязательные):

```python
class UserSeason(models.Model):
    user = FK(User)
    season = FK(Season)
    watch_status = IntegerChoices: WATCHED=1, PLAN=2, SKIP=3  # как UserMovie
    rating = PositiveSmallIntegerField(1-10, null=True)
    note = TextField(blank=True)
    updated_at = DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'season']
```

**Где реализовать:** В `TMDBMovieSyncService.sync_movie()` после `_sync_seasons_and_episodes()` вызывать `_sync_season_statuses(movie, user)` — для текущего пользователя (или всех пользователей, у которых есть UserMovie на этом сериале).

**API для UI:**
- `PATCH /api/vault/seasons/{id}/status` —toggle watch_status + rating
- В `SeasonOut` добавить `user_state: UserSeasonStateOut` (watch_status, rating)

---

### Этап 5: Модель UserSeason — Приоритет: ВЫСОКИЙ (обязательно для UI)

Нужна модель для хранения пользовательских статусов и оценок по сезонам:

```python
class UserSeason(models.Model):
    """Пользовательский статус сезона: просмотрен/планирую/пропущу + оценка"""
    class WatchStatus(models.IntegerChoices):
        WATCHED = 1, 'Просмотрено'
        PLAN = 2, 'Буду смотреть'
        SKIP = 3, 'Не буду смотреть'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_seasons')
    season = models.ForeignKey('Season', on_delete=models.CASCADE, related_name='user_seasons')
    watch_status = models.PositiveSmallIntegerField('Статус просмотра', choices=WatchStatus, null=True, blank=True)
    rating = models.PositiveSmallIntegerField('Оценка', validators=[MinValueValidator(1), MaxValueValidator(10)], null=True, blank=True)
    note = models.TextField('Заметка', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'season']
        indexes = [models.Index(fields=['user', 'watch_status'])]
```

#### 5.1 Миграция
- `python manage.py makemigrations vault`
- Имя: `0013_userseason` (следующая после `0012_season_source`)

#### 5.2 API схемы (в `vault/api.py`)
```python
class UserSeasonStateOut(Schema):
    watch_status: str | None  # "watched" | "plan" | "skip" | null
    rating: int | None = None

class SeasonOut(Schema):
    id: int
    season_number: int
    title: str
    description: str
    release_date: str | None
    poster_url: str | None
    episodes_count: int
    air_year: int | None
    user_state: UserSeasonStateOut

class SetSeasonStatusIn(Schema):
    watch_status: str | None = None  # "watched" | "plan" | "skip" | null для снятия
    rating: int | None = None  # null = снять оценку

class SetSeasonStatusOut(Schema):
    season_id: int
    user_state: UserSeasonStateOut
```

#### 5.3 API эндпоинты
```
PATCH /api/vault/seasons/{id}/status     → SetSeasonStatusOut  (body: SetSeasonStatusIn)
```

#### 5.4 Миграция clear_vault_data
Добавить `UserSeason` в список `to_purge` — иначе при очистке данных мусор останется.

#### 5.5 Service слой: `vault/services/season_status_service.py`
```python
class SeasonStatusService:
    @staticmethod
    def get_or_create_user_state(user, season):
        return UserSeason.objects.get_or_create(user=user, season=season)

    @staticmethod
    def get_season_state(user, season):
        obj = UserSeason.objects.filter(user=user, season=season).first()
        if not obj:
            return {"watch_status": None, "rating": None}
        return {"watch_status": obj.get_watch_status_display_key(), "rating": obj.rating}

    @staticmethod
    @transaction.atomic
    def set_season_status(user, season, watch_status=None, rating=None):
        obj, _ = UserSeason.objects.get_or_create(user=user, season=season)
        if watch_status is not None:
            obj.watch_status = UserSeason.WatchStatus.WATCHED if watch_status == "watched" else ...
        if rating is not None:
            obj.rating = rating
        obj.save()
        return obj
```

#### 5.6 Интеграция в TMDB Sync
В `TMDBMovieSyncService` после создания сезонов вызвать:
```python
cls._sync_season_user_statuses(movie, user)
```
Где для всех UserMovie этого movie:
- `WATCHED` → создать UserSeason с `WATCHED` для всех новых сезонов
- `PLAN` → создать UserSeason с `PLAN`
- `SKIP` → создать UserSeason с `SKIP`
- null/отсутствует → не создавать (или WATCHED=None)

---

## Порядок выполнения (рекомендуемый)

| # | Задача | Файлы | Зависимости | Статус |
|---|--------|-------|-------------|--------|
| 1 | API схемы + эндпоинты сезонов + UserSeason | `vault/api.py`, `vault/models.py` | — | **✅ ГОТОВ** |
| 2 | Модель UserSeason + миграция + очистка | `vault/models.py`, `vault/management/commands/clear_vault_data.py` | — | **✅ ГОТОВ** |
| 3 | Service слой для статусов сезонов | `vault/services/season_status_service.py` | 2 | **✅ ГОТОВ** |
| 4 | API эндпоинты CRUD статусов сезонов | `vault/api.py` | 1, 2, 3 | **✅ ГОТОВ** |
| 5 | TMDB sync: загрузка сезонов + синхронизация статусов | `vault/services/tmdb_movie_sync_service.py` | 3, 4 | **✅ ГОТОВ** |
| 6 | Frontend: блок сезонов на карточке сериала | `front/src/routes/(vault)/movies/[slug]/+page.svelte` + `+page.ts` | 1, 4 | **✅ ГОТОВ** |
| 7 | (Опц.) Импорт UserSeason при bulk-операциях | `vault/services/movie_status_service.py` | 5 | ❌ ЕЩЁ НЕ НАЧАТ |

## Приоритеты выполнения:
1. **Бэкенд-first**: сначала модели + API + sync, потом UI
2. UserSeason нужен раньше UI (иначе UI нечего сохранять)
3. TMDB sync синхронизуает статусы только для существующих UserSeason или создает новые на основе UserMovie

---

## Технические детали и риски

### TMDB API для сезонов
```python
# Получить детали сериала с сезонами
tv = tmdb.tv_show(tmdb_id)  # уже есть в details.seasons

# Или отдельно загрузить сезон
season_details = tmdb.tv_show_season(tmdb_id, season_number)
# season_details.episodes → список эпизодов
```

### Производительность
- Синхронизация сезонов может быть медленной (много запросов к TMDB)
- Рассмотреть: асинхронная задача (Celery/RQ) или фоновый таск
- Кэширование: `tmdb_last_synced_at` уже есть, использовать для пропуска

### Конфликт данных
- Kinorium CSV не имеет сезонов → только TMDB
- При повторном sync: обновлять существующие Season/Episode (upsert по season_number/episode_number)

### Миграции
- Модели Season/Episode уже созданы (миграция 0007)
- Новые поля/индексы не нужны

---

## Чек-лист готовности к старту

- [x] Модели БД: `Season`, `Episode` — готовы
- [x] Поля в `Movie`: `seasons_count`, `episodes_count` — готовы
- [x] TMDB sync заполняет счетчики — готово
- [x] **ЭТАП 1 ВЫПОЛНЕН:**
  - [x] Модель `UserSeason` — создана в `vault/models.py` (модель + миграция `0020_userseason`)
  - [x] API схемы: `SeasonOut`, `EpisodeOut`, `UserSeasonStateOut`, `SetSeasonStatusIn/Out` — добавлены в `vault/api.py`
  - [x] API эндпоинты реализованы:
    - `GET /api/vault/movies/{slug}/seasons` → `list[SeasonOut]`
    - `GET /api/vault/seasons/{season_id}/episodes` → `list[EpisodeOut]`
    - `PATCH /api/vault/seasons/{season_id}/status` → `SetSeasonStatusOut`
  - [x] `MovieDetailOut` расширен полем `seasons: list[SeasonOut]`
  - [x] Service слой: `vault/services/season_status_service.py` (`SeasonStatusService`)
  - [x] `clear_vault_data`: `UserSeason` добавлен в очистку
  - [x] Миграция применена (`vault.0020_userseason`)
  - [x] Тесты пройдены (18 tests OK)
- [x] **ЭТАП 2 ВЫПОЛНЕН:**
  - [x] TMDB sync: загрузка сезонов + upsert UserSeason на основе UserMovie
    - [x] `_sync_seasons_and_episodes()` добавлен в `TMDBMovieSyncService`
    - [x] `_sync_episodes()` — синхронизация эпизодов внутри сезона
    - [x] `_sync_season_user_statuses()` — маркировка сезонов на основе `UserMovie.watch_status`
    - [x] Интегрировано в `sync_movie()` для TV типов
    - [x] Orphan cleanup (удаление сезонов/эпизодов, которых больше нет в TMDB)
    - [x] Тесты пройдены (18 tests OK)
- [x] **ЭТАП 3 ВЫПОЛНЕН:**
  - [x] Frontend: блок сезонов (Accordion + rating + watch toggle)
    - [x] `+page.ts`: добавлено поле `seasons` в `ApiMovieDetail`
  - [x] `+page.svelte`: добавлен блок "Сезоны" для сериалов (только если `movie_type === "series" && seasons.length > 0`)
    - [x] Каждый сезон оформлен в виде карточки (`Card` + `CardContent`) с постером сезона
    - [x] На каждом сезоне: номер, название, год, количество серий, toggle "Просмотрено" + StarRating
    - [x] `setSeasonStatus()` и `setSeasonRating()` — PATCH запросы к API
    - [x] CSS: `vd-season-*` стили (grid, card, poster, actions) в `vault-detail.css`