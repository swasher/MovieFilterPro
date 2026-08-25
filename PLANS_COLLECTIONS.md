# План: Коллекции TMDB (`belongs_to_collection`)

> Идея пользователя: при первичной синхронизации фильма с TMDB, если `belongs_to_collection != null`, делаем дополнительный запрос `collections_get_details(collection_id)`, кэшируем название + постер коллекции локально. На странице фильма показываем блок коллекции. При клике на фильм из коллекции: есть локально — переход на `/movies/{slug}`, нет — алерт "фильма нет в базе, добавить?" с импортом.

Пример JSON TMDB (коллекция 528 — Terminator):
```json
{
  "id": 528,
  "name": "The Terminator Collection",
  "overview": "A series of science-fiction films...",
  "poster_path": "/kpZxdNsAV7qTdTLwKM5NLqa7GEo.jpg",
  "backdrop_path": "/sCnBEw2Yu6foEjs4Xb4eMddYHRo.jpg",
  "parts": [
    { "id": 218, "title": "The Terminator", "poster_path": "/qvkt...", "release_date": "1984-10-26", "media_type": "movie" },
    { "id": 280, "title": "Terminator 2: Judgment Day", "poster_path": "/jFTV...", "release_date": "1991-07-03", "media_type": "movie" }
  ]
}
```

---

## 1. Технический контекст (чтобы не искать заново)

### 1.1 Текущее состояние — коллекций нет

| Что | Где | Статус |
|-----|-----|--------|
| Модель `Collection` | `vault/models.py:102-271` (`Movie`, `Person`, `Season`...) | **нет** |
| Поле `collection` на `Movie` | `vault/models.py:104` | **нет** |
| Обработка `belongs_to_collection` в sync | `vault/services/tmdb_movie_sync_service.py:211-252` (`_apply_movie_payload`) | **нет, игнорируется** |
| API отдача коллекции | `vault/api.py:45-82` (`MovieDetailOut`) | **нет** |
| UI коллекции | `front/src/routes/(vault)/movies/[slug]/+page.svelte:1-1521` | **нет** |
| TODO упоминание | `TODO.md:110` | `belongs_to_collection (отображать сразу коллекции?)` |
| Единственное вхождение `collection` в коде | `kinozal_scan/parse.py:189` | комментарий про "Коллекция" в заголовке Kinozal |

### 1.2 TMDB-библиотека `tmdbapis` (форк `swasher/TMDbAPIs`, в `.venv`)

- Класс `Collection` — `tmdbapis/objs/reload.py:117`: поля `id`, `name`, `overview`, `poster_path`, `poster_url`, `backdrop_path`, `backdrop_url`, `movies`/`parts`, `translations`.
- Поле на объекте фильма — `tmdbapis/objs/reload.py:558`: `self.collection = self._parse(attrs="belongs_to_collection", value_type="collection")`. После `tmdb.movie(tmdb_id)` → `details.collection` это `Collection | None` (парсится из JSON `belongs_to_collection: {id, name, poster_path, backdrop_path}`).
- Детальный запрос — `tmdbapis/api3.py:549`: `collections_get_details(collection_id, ...)` → возвращает `Collection` с полем `parts` (список `Movie` объектов коллекции). Альтернативный низкоуровневый путь через `tmdb.collection(collection_id)` если есть.
- Проверка: `tmdb_adapter/client_singleton.py:1-42` — `get_tmdb_client()` возвращает `TMDbAPIs(api_key, v4_access_token, language="RU")`.

### 1.3 Модели Vault

`vault/models.py:104-271` — центральная модель `Movie`:

```python
class Movie(models.Model):
    title, original_title, slug, description, year, movie_type, status,
    poster, backdrop_path, genres(M2M), countries(M2M),
    tmdb_id, tmdb_media_type, tmdb_last_synced_at, source, ...
    # poster хранит относительный путь TMDB, URL собирается через _build_tmdb_image_url
```

Хелпер `vault/models.py:26-42` — `_build_tmdb_image_url(raw_path, size)` (`TMDB_IMAGE_BASE_URL` + `TMDB_IMAGE_SIZE` из `settings`).

### 1.4 Sync-сервис

`vault/services/tmdb_movie_sync_service.py:50-180` — `TMDBMovieSyncService.sync_movie(movie, force_rematch, selected_candidate)`:

1. Резолв кандидата (stored `tmdb_id` / `TMDBMovieMatchingService.match_movie()` / ручной `selected_candidate`).
2. `_load_details(tmdb, candidate)` → `tmdb.movie(id)` или `tmdb.tv_show(id)` (с fallback на другой тип).
3. `_apply_movie_payload` или `_apply_tv_payload` + `_field_setter`.
4. Синк связей: genres, countries, persons, seasons/episodes.
5. `_cleanup_orphan_persons`.

`_apply_movie_payload:211` сейчас сетит `title`, `poster`, `budget`, `homepage`, `tmdb_vote_*` и т.д., но **не трогает коллекцию**.

### 1.5 Import-сервис

`vault/services/tmdb_movie_import_service.py:114-180` — `TMDBMovieImportService.import_movie(tmdb_id, media_type)` создаёт `Movie(source=TMDB)` и вызывает `sync_movie(force_rematch=True)`.

### 1.6 API

`vault/api.py:722-799` — `movie_detail(slug) -> MovieDetailOut`:

```python
class MovieDetailOut(Schema):
    id, title, original_title, year, slug, description, movie_type, ...
    poster_url, backdrop_url, tmdb_id, tmdb_linked, genres, countries, keywords,
    user_state: UserStateOut, custom_lists, directors, actors, seasons
```

Хелперы: `_tmdb_image_url:453`, `_build_user_state:414`, `_build_movie_out:540`.

Фронт лоадер: `front/src/routes/(vault)/movies/[slug]/+page.ts:85` — `fetch('/api/vault/movies/{slug}') -> ApiMovieDetail`.

### 1.7 Фронт — страница фильма

`front/src/routes/(vault)/movies/[slug]/+page.svelte:41-723` — Svelte 5 runes (`$derived`, `$state`, `$effect`):

- Лейаут: 2 колонки (`vd-sidebar` + main), секции `vd-title-block`, `vd-facts-row`, `Seasons`, `Crew`, `vd-service-row`.
- Стили: `front/src/routes/(vault)/vault-detail.css:1-437` (классы `vd-card`, `vd-section`, `vd-chip`...).
- Компоненты: `PersonCard`, `SeasonStatus`, shadcn `Card`, `Badge`, `Dialog`, `Tooltip`, `ImageZoom`.

---

## 2. Подводные камни

1. **Отсутствующие фильмы коллекции** — главный камень. В коллекции 5-10 фильмов TMDB, в Vault может быть 1-2. Решение: кэшируем `parts` локально (см. модель), при отдаче метим `in_vault` + `vault_slug`.
2. **Атомарность sync** — `sync_movie` уже `@transaction.atomic` (`tmdb_movie_sync_service.py:54`). Добавление коллекции не должно ломать транзакцию при ошибке TMDB (fallback: логируем, не падуем sync).
3. **TV vs Movie** — `belongs_to_collection` бывает и у `tv` (редко). Поддержать только `movie` на первом этапе, для `tv` — пропускать или логировать.
4. **Отвязка** — если TMDB вернул `belongs_to_collection = null`, надо отвязать `movie.collection = None` (но не удалять `Collection` — на неё могут ссылаться другие фильмы).
5. **Orphan-коллекции** — `Collection` без `Movie` можно хранить (дешёво) или чистить кроном. Предпочтение: хранить, чистить опционально.
6. **Порядок в коллекции** — TMDB `parts` не всегда отсортированы по дате. Сортировать по `release_date` или сохранять `order` как в `parts`.
7. **Постер коллекции может быть null** — fallback на placeholder как у `movie.poster_url`.
8. **Rate limit TMDB** — один доп. запрос на фильм при sync — ок. Не делать N запросов за раз в очереди.
9. **Re-sync** — при повторном sync коллекция может смениться (фильм переехал в другую коллекцию). Обновлять FK и метаданные.

---

## 3. План реализации

### Этап 1 — Модели + миграция

**Файл:** `vault/models.py`

```python
class Collection(models.Model):
    tmdb_id = models.PositiveIntegerField("TMDB ID", unique=True, db_index=True)
    name = models.CharField("Название", max_length=500)
    overview = models.TextField("Описание", blank=True, default="")
    poster_path = models.CharField("Путь к постеру", max_length=500, blank=True, null=True)
    backdrop_path = models.CharField("Путь к бэкдропу", max_length=500, blank=True, null=True)
    # опционально: original_name, original_language — не нужно для MVP
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def poster_url(self): return _build_tmdb_image_url(self.poster_path, getattr(settings, 'TMDB_IMAGE_SIZE', 'w500'))
    def get_poster_url(self, size='w500'): return _build_tmdb_image_url(self.poster_path, size)
    @property
    def backdrop_url(self): return _build_tmdb_image_url(self.backdrop_path, 'w1280')

    class Meta:
        verbose_name = "Коллекция"
        verbose_name_plural = "Коллекции"
        ordering = ["name"]

class CollectionPart(models.Model):
    """Кэшированный элемент коллекции из TMDB parts (для отображения отсутствующих)."""
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name="parts")
    tmdb_id = models.PositiveIntegerField("TMDB ID фильма")
    title = models.CharField(max_length=500)
    original_title = models.CharField(max_length=500, blank=True, default="")
    poster_path = models.CharField(max_length=500, blank=True, null=True)
    release_date = models.DateField(null=True, blank=True)
    order = models.PositiveSmallIntegerField(default=0)  # позиция в parts

    @property
    def poster_url(self): return _build_tmdb_image_url(self.poster_path, 'w500')

    class Meta:
        unique_together = [("collection", "tmdb_id")]
        ordering = ["order", "release_date", "title"]
```

На `Movie` добавить:

```python
collection = models.ForeignKey(Collection, null=True, blank=True, on_delete=models.SET_NULL, related_name="movies")
```

Миграция: `uv run python manage.py makemigrations vault` + `migrate`.

**Альтернатива без `CollectionPart`:** хранить `parts` как `JSONField` на `Collection`. Проще, но хуже для запросов. Рекомендуется отдельная таблица (как выше) — дёшево и явно.

### Этап 2 — Сервис коллекций

**Новый файл:** `vault/services/collection_service.py`

```python
class CollectionService:
    @classmethod
    def sync_collection_for_movie(cls, movie: Movie, tmdb_collection_obj) -> Collection | None:
        """Создаёт/обновляет Collection + CollectionPart из tmdb_collection_obj (belongs_to_collection)."""
        # 1. get_or_create Collection по tmdb_id
        # 2. обновить name/overview/poster_path/backdrop_path если изменились
        # 3. вызвать _sync_parts(collection) — см. ниже
        # 4. привязать movie.collection = collection
        # Возвращает Collection или None если tmdb_collection_obj is None (тогда movie.collection = None)

    @classmethod
    def _sync_parts(cls, collection: Collection) -> bool:
        """Делает tmdb.collections_get_details(collection.tmdb_id), синхронизирует CollectionPart.
        Возвращает True если были изменения. Логирует, не кидает наружу."""
        # tmdb = get_tmdb_client()
        # details = tmdb.collections_get_details(collection.tmdb_id)  # или tmdb.collection(...)
        # parts = getattr(details, "parts", None) or getattr(details, "movies", None) or []
        # upsert CollectionPart по (collection, tmdb_id), удалить orphaned, обновить order
```

Логика `_sync_parts`: удалить `CollectionPart` которых нет в новом `parts`, upsert остальных, сохранить `order` по индексу в массиве.

**Интеграция в sync:**

`vault/services/tmdb_movie_sync_service.py`:

- В `sync_movie` после `set_field("tmdb_id"...)` и перед/после `_apply_movie_payload` — вызвать `_sync_collection(movie, details)`.
- Добавить метод `_sync_collection(cls, movie, details)`:
  ```python
  @classmethod
  def _sync_collection(cls, movie: Movie, details) -> bool:
      raw = getattr(details, "collection", None)  # или belongs_to_collection
      if raw is None:
          # raw может быть dict или Collection
          raw = getattr(details, "belongs_to_collection", None)
      if raw is None and isinstance(details, dict):
          raw = details.get("belongs_to_collection")
      # если None — отвязать
      # если объект — делегировать CollectionService.sync_collection_for_movie
      # обернуть в try/except, логировать, не падать
  ```
- Учесть `media_type == "tv"` — пока пропускать (или тоже синкать, но флаг `is_tv_collection`).

### Этап 3 — API

**Файл:** `vault/api.py`

Схемы:

```python
class CollectionPartOut(Schema):
    tmdb_id: int
    title: str
    year: int | None = None
    poster_url: str | None = None
    in_vault: bool
    vault_slug: str | None = None

class CollectionBriefOut(Schema):
    tmdb_id: int
    name: str
    overview: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    parts: list[CollectionPartOut] = []
```

Расширить `MovieDetailOut:45` — добавить поле:

```python
collection: CollectionBriefOut | None = None
```

В `movie_detail:722` — собрать:

```python
collection_out = None
if movie.collection_id:
    coll = movie.collection
    # parts из CollectionPart, отсортированные по order
    # для каждого part: in_vault = Movie.objects.filter(tmdb_id=part.tmdb_id).exists()
    # vault_slug — из того же запроса (prefetch)
    # собрать CollectionBriefOut
```

Добавить хелпер `_build_collection_out(movie) -> CollectionBriefOut | None`.

**Импорт отсутствующего фильма:**

Переиспользовать существующий `POST /api/vault/tmdb/import` (`vault/api.py:971`, `TMDBMovieImportService.import_movie`). Отдельный endpoint для коллекции не нужен. Фронт просто вызовет `POST /api/vault/tmdb/import` с `{tmdb_id, media_type: "movie"}`.

Опционально: `POST /api/vault/collections/{tmdb_id}/refresh` — форсированный рефреш метаданных коллекции (для админа).

### Этап 4 — Frontend

**Файлы:**

- `front/src/routes/(vault)/movies/[slug]/+page.ts:1-96` — расширить `ApiMovieDetail`:
  ```ts
  collection: {
    tmdb_id: number; name: string; overview: string | null;
    poster_url: string | null; backdrop_url: string | null;
    parts: Array<{ tmdb_id: number; title: string; year: number | null; poster_url: string | null; in_vault: boolean; vault_slug: string | null }>;
  } | null;
  ```

- `front/src/routes/(vault)/movies/[slug]/+page.svelte` — новая секция после `Seasons` / перед `Crew` (или после):

  ```svelte
  {#if movie.collection}
    <Card class="vd-card">
      <CardHeader>
        <CardTitle class="text-xl">Коллекция — {movie.collection.name}</CardTitle>
        {#if movie.collection.overview}<CardDescription>{movie.collection.overview}</CardDescription>{/if}
      </CardHeader>
      <CardContent>
        <div class="vd-collection-grid flex gap-3 overflow-x-auto pb-2">
          {#each movie.collection.parts as part}
            {#if part.in_vault && part.vault_slug}
              <a href="/movies/{part.vault_slug}" class="vd-collection-card">
                <img src={part.poster_url} alt={part.title} />
                <span>{part.title} ({part.year ?? "—"})</span>
              </a>
            {:else}
              <button class="vd-collection-card vd-collection-card--missing opacity-60" onclick={() => handleMissingClick(part)}>
                <img src={part.poster_url} alt={part.title} />
                <span>{part.title}</span>
              </button>
            {/if}
          {/each}
        </div>
      </CardContent>
    </Card>
  {/if}
  ```

- Логика `handleMissingClick`:
  ```ts
  const handleMissingClick = async (part) => {
    if (confirm(`Фильма "${part.title}" нет в базе. Добавить из TMDB?`)) {
      const res = await fetch("/api/vault/tmdb/import", {
        method: "POST", headers: {"Content-Type":"application/json"},
        body: JSON.stringify({ tmdb_id: part.tmdb_id, media_type: "movie" })
      });
      const data = await res.json();
      if (res.ok && data.movie?.slug) {
        toast.success(data.message);
        await goto(`/movies/${data.movie.slug}`);
      } else {
        toast.error(data.message ?? "Не удалось импортировать");
      }
    }
  };
  ```

- Стили: расширить `vault-detail.css` — `vd-collection-grid`, `vd-collection-card` (по образцу `vd-season-card`, `vd-crew-grid`).

- Отдельная страница коллекции **не нужна** для MVP (по идее пользователя). Если понадобится — `front/src/routes/(vault)/collections/[tmdb_id]/+page.svelte`.

### Этап 5 — Миграция данных / backfill

- Для существующих `Movie` с `tmdb_id` — команда `uv run python manage.py sync_collections --all` или реюз `tmdb-sync` очереди: при следующем `sync_movie` коллекция подтянется автоматически.
- Команда:
  ```python
  # vault/management/commands/sync_collections.py
  class Command(BaseCommand):
      def handle(self, *args, **options):
          for movie in Movie.objects.filter(tmdb_id__isnull=False):
              try: TMDBMovieSyncService.sync_movie(movie)
              except Exception: continue
  ```

### Этап 6 — Тесты

- `vault/tests/test_collection_service.py` — юнит на `sync_collection_for_movie` (создание, обновление, отвязка, parts sync).
- `vault/tests/test_tmdb_movie_sync_service.py` — мок `tmdb.movie()` с `belongs_to_collection`, проверить что `movie.collection` сетится.
- `vault/tests/test_api_collection.py` — `GET /api/vault/movies/{slug}` отдаёт `collection`.

---

## 4. Порядок работ (чеклист для агента)

- [ ] 1. Создать модели `Collection` + `CollectionPart`, FK на `Movie`, миграция.
- [ ] 2. Создать `vault/services/collection_service.py` (`sync_collection_for_movie`, `_sync_parts`).
- [ ] 3. Интегрировать в `TMDBMovieSyncService.sync_movie` → `_sync_collection` (try/except, не ломать основной sync).
- [ ] 4. Расширить `vault/api.py` — схемы `CollectionBriefOut`/`CollectionPartOut`, поле `collection` в `MovieDetailOut`, хелпер `_build_collection_out`.
- [ ] 5. Расширить `front/src/routes/(vault)/movies/[slug]/+page.ts` (тип) + `+page.svelte` (UI блок, `handleMissingClick` с `POST /api/vault/tmdb/import`).
- [ ] 6. Стили в `vault-detail.css`.
- [ ] 7. Ручная проверка: синхронизировать фильм из коллекции (например Terminator 218), открыть страницу, кликнуть на отсутствующий → алерт → импорт → переход.
- [ ] 8. (Опционально) management command `sync_collections` для backfill.
- [ ] 9. Тесты.

---

## 5. Что НЕ делать

- Не создавать отдельную страницу `/collections/{id}` в MVP.
- Не менять `Movie` поля кроме `collection` FK.
- Не трогать `front/` вне `movies/[slug]` без запроса.
- Не менять `tmdb_adapter/client_singleton.py` (только использовать `get_tmdb_client()`).
- Не удалять/переписывать существующие комментарии и логику sync без необходимости.

---

## 6. Открытые вопросы (решить перед стартом или в процессе)

1. Нужен ли `backdrop_path` коллекции на бэке? (TMDB отдаёт — хранить, но не показывать в MVP.)
2. Чистить ли orphan `Collection` (0 фильмов)? Предложение: не чистить.
3. Поддерживать ли TV-коллекции? Предложение: MVP — только `movie`, для `tv` пропускать.
