# PLANS-VAULT-FILTER.md — Фильтрация элементов на странице /vault

---

## 0. Текущее состояние

- Эндпоинт `GET /api/vault/movies` уже поддерживает фильтрацию по:
  - `genre` (один slug жанра)
  - `status` (watched / will_watch / wont_watch / favorites)
  - `list` (ID пользовательского списка)
  - `q` (поиск по названию)
  - `order` (сортировка)
- Фронтенд (`front/src/routes/(vault)/+page.svelte`) имеет:
  - строку поиска
  - dropdown сортировки
  - переключатель вида (grid/table)
  - кнопки статуса в сайдбаре
  - ссылки списков в сайдбаре
- **Чего нет**: модальное окно фильтрации с комбинированными параметрами (мульти-жанр, диапазон лет, тип контента, статус просмотра).

---

## 1. Что реализуем

Кнопка «Фильтр» рядом с кнопкой сортировки. При нажатии открывается модальное окно (Dialog) со следующими контролами:

| Контрол | Тип | Значения по умолчанию |
|---|---|---|
| Жанр | Список с чекбоксами (мульти) | Все |
| Год от | Number input | пусто |
| Год до | Number input | пусто |
| Тип | RadioGroup (Фильм / Сериал / Не важно) | Не важно |
| Просмотрено | RadioGroup (Просмотрено / Не просмотрено / Не важно) | Не важно |
| Любимые | Checkbox | Снят |
| Список | Select (список пользовательских списков) | Не важно |

Кнопки **«Применить»** и **«Сбросить»** в footer диалога.

---

## 2. Изменения на бэкенде

### 2.1. `vault/api.py` — расширение `list_movies`

Добавить новые query-параметры к эндпоинту `GET /api/vault/movies`:

| Параметр | Тип | Описание |
|---|---|---|
| `genre` | `list[str]` | Один или несколько slug жанров (повторяющиеся query-параметры) |
| `year_from` | `int` | Минимальный год выпуска |
| `year_to` | `int` | Максимальный год выпуска |
| `movie_type` | `str` | Один из: `movie`, `series`, `cartoon`, `anime`, `show` |
| `is_favorite` | `bool` | Только избранные (`true`/`false`) |
| `watch_status` | `str` | `watched` (просмотренные) или `not_watched` (непросмотренные). Отсутствие параметра = «не важно» |

**Логика:**
- `genre`: мульти-выбор через повторяющиеся query-параметры (`?genre=comedy&genre=action`). Применять `Q(genres__slug__in=genres)` + `.distinct()`.
- `year_from` / `year_to`: `Q(year__gte=year_from)` и `Q(year__lte=year_to)`.
- `movie_type`: `Q(movie_type=movie_type)`.
- `is_favorite`: `Q(user_movies__user=user, user_movies__is_favorite=True)`.
- `watch_status`:
  - `watched` — только просмотренные (`user_movies.watch_status = WATCHED`)
  - `not_watched` — только непросмотренные (исключение: `NOT(user_movies.watch_status = WATCHED)`; записи без `UserMovie` тоже считаются непросмотренными)
  - параметр отсутствует — «не важно», фильтр не применяется

**Важно:** текущий `list_movies` уже вызывает `.distinct()` в конце — нужно убедиться, что мульти-жанр не ломает пагинацию/лимит. Порядок фильтрации: сначала все `filter()`, потом `.distinct()`, потом `.order_by()`, потом `[:limit]`.

**Замечание по `watch_status=not_watched`**: это негативная фильтрация. Для корректной работы нужно использовать `~Q(...)` (NOT) или LEFT OUTER JOIN с условием. Модель `UserMovie` имеет `unique_together=(user, movie)`, поэтому у каждого пользователя для каждого фильма не более одной записи. Если у пользователя нет записи `UserMovie` для фильма — фильм считается «не просмотренным».

### 2.2. `vault/api.py` — Schema для `MovieOut` (опционально)

Нет необходимости менять `MovieOut` — он уже возвращает все нужные поля (`movie_type`, `year`, `genres` не нужны в листе).

---

## 3. Изменения на фронтенде

### 3.1. `front/src/routes/(vault)/+page.svelte`

**3.1.1. Состояние (state)**

Добавить новые state-переменные:

```svelte
let filterOpen = $state(false);
let selectedGenres = $state<string[]>([]);
let yearFrom = $state<string>("");
let yearTo = $state<string>("");
let selectedMovieType = $state<string>(""); // "", "movie", "series", "cartoon", "anime", "show"
let selectedWatchStatus = $state<string>(""); // "", "watched", "not_watched"
let isFavorite = $state(false);
let selectedList = $state<string>(""); // "", list_id
```

Инициализировать значения из URL query params при загрузке страницы (аналогично тому, как сейчас делается `activeOrder` и `searchQuery` через `$effect`).

**3.1.2. Кнопка «Фильтр»**

Добавить кнопку рядом с кнопкой сортировки (между переключателем вида и кнопкой «Add movie»):

```svelte
<Button variant="outline" class="h-11" onclick={() => filterOpen = true}>
  <Filter class="size-4" />
  Фильтр
</Button>
```

**3.1.3. Модальное окно (Dialog)**

Использовать существующий `Dialog` из shadcn-svelte. Структура:

```
Dialog.Root bind:open={filterOpen}
  Dialog.Header
    Dialog.Title "Фильтры"
    Dialog.Description "Настрой фильтрацию списка фильмов"
  Dialog.Content
    // разделы:
    // 1. Жанр — список с чекбоксами из data.genres (мульти-выбор)
    // 2. Год — два Input type="number" (от / до)
    // 3. Тип — RadioGroup (Фильм / Сериал / Не важно)
    // 4. Просмотрено — RadioGroup (Просмотрено / Не просмотрено / Не важно)
    // 5. Любимые — Checkbox
    // 6. Список — Select с пользовательскими списками
  Dialog.Footer
    Button variant="outline" onclick={resetFilters} "Сбросить"
    Button onclick={applyFilters} "Применить"
```

**3.1.4. Функция `applyFilters()`**

Собирает все активные фильтры в `URLSearchParams`, обновляет URL через `goto()`:

```svelte
const applyFilters = async () => {
  const params = new URLSearchParams(window.location.search);

  // genre: передать как повторяющиеся query-параметры
  params.delete("genre");
  selectedGenres.forEach(g => params.append("genre", g));

  // year range
  if (yearFrom) params.set("year_from", yearFrom); else params.delete("year_from");
  if (yearTo) params.set("year_to", yearTo); else params.delete("year_to");

  // movie_type
  if (selectedMovieType) params.set("movie_type", selectedMovieType); else params.delete("movie_type");

  // watch_status
  if (selectedWatchStatus) params.set("watch_status", selectedWatchStatus); else params.delete("watch_status");

  // is_favorite
  if (isFavorite) params.set("is_favorite", "true"); else params.delete("is_favorite");

  // list
  if (selectedList) params.set("list", selectedList); else params.delete("list");

  // сбросить page при смене фильтров
  params.delete("page");

  const queryString = params.toString();
  await goto(queryString ? `/?${queryString}` : "/", {
    replaceState: true, keepFocus: true, noScroll: true, invalidateAll: true
  });
  filterOpen = false;
};
```

**3.1.5. Функция `resetFilters()`**

Сбрасывает все state-переменные в значения по умолчанию и вызывает `applyFilters()` (или просто очищает URL).

**3.1.6. Синхронизация state с URL**

Добавить `$effect`, который читает URL params и устанавливает state при загрузке / при изменении URL (аналогично текущему паттерну с `activeOrder` и `searchQuery`).

**3.1.7. Отображение активных фильтров**

Под кнопками управления (рядом с текущими лейблами жанра/списка/поиска) показать pill-бейджи активных фильтров, например:
- `Жанр: Комедия ×`
- `Год: 2020–2025 ×`
- `Тип: Фильм ×`
- `Просмотрено: Да ×`

Каждый pill — кнопка для сброса этого конкретного фильтра.

---

### 3.2. `front/src/routes/(vault)/+page.ts`

Добавить чтение новых query-параметров:

```ts
const genre = url.searchParams.getAll("genre");
const yearFrom = url.searchParams.get("year_from") ?? "";
const yearTo = url.searchParams.get("year_to") ?? "";
const movieType = url.searchParams.get("movie_type") ?? "";
const watchStatus = url.searchParams.get("watch_status") ?? "";
const isFavorite = url.searchParams.get("is_favorite") === "true";
const list = url.searchParams.get("list") ?? "";
```

Пробрасывать их в запрос к `/api/vault/movies`.

Для `genre` — передавать как повторяющиеся параметры (`?genre=comedy&genre=action`). Это нативно поддерживается `URLSearchParams.getAll()`.

---

### 3.3. `vault/api.py` — чтение мульти-жанра

В `list_movies` прочитать `genre` как список:

```python
# Django Ninja автоматически парсит повторяющиеся query-параметры в list,
# если аннотировать как list[str]
genre: list[str] | None = None,
```

Или, если используется строка через запятую:

```python
genre: str | None = None,
# ...
if genre:
    genre_slugs = [g.strip() for g in genre.split(",") if g.strip()]
    if genre_slugs:
        qs = qs.filter(genres__slug__in=genre_slugs)
```

**Рекомендация**: использовать `list[str]` — Django Ninja поддерживает это нативно через повторяющиеся query-параметры.

---

## 4. Порядок реализации (последовательность)

### Шаг 1: Бэкенд — новые параметры фильтрации в API

- [ ] Добавить `genre: list[str] | None = None`, `year_from`, `year_to`, `movie_type` к `list_movies` в `vault/api.py`
- [ ] Добавить логику фильтрации по жанрам (мульти), году, типу
- [ ] Проверить что `.distinct()` корректно работает с мульти-жанром
- [ ] Протестировать через `curl` или браузер: `GET /api/vault/movies?genre=comedy&genre=action&year_from=2020&year_to=2025&movie_type=movie`

### Шаг 2: Фронтенд — состояние фильтра и URL params

- [ ] Добавить state-переменные для всех фильтров в `+page.svelte`
- [ ] Добавить чтение URL params в `+page.ts`
- [ ] Пробросить новые параметры в API-запрос
- [ ] Синхронизировать state с URL через `$effect`

### Шаг 3: Фронтенд — кнопка «Фильтр» и модальное окно

- [ ] Добавить кнопку «Фильтр» рядом с кнопкой сортировки
- [ ] Создать Dialog с контролами (жанр, год, тип, статус, список)
- [ ] Реализовать `applyFilters()` — сбор URL params и навигация
- [ ] Реализовать `resetFilters()` — очистка всех фильтров

### Шаг 4: Фронтенд — отображение активных фильтров

- [ ] Показывать pill-бейджи активных фильтров под строкой поиска
- [ ] Каждый pill — кнопка для сброса конкретного фильтра

### Шаг 5: Полировка

- [ ] Закрытие диалога по Escape / клик на оверлей
- [ ] Сохранение состояния фильтров при навигации (URL — единственный source of truth)
- [ ] Проверка что все фильтры стакаются корректно (жанр + год + тип + статус + список + поиск + сортировка)

---

## 5. Зависимости и замечания

### 5.1. shadcn-svelte компоненты

Для реализации понадобятся (все уже есть в проекте):
- `Dialog` — модальное окно фильтра
- `Button` — кнопки применить/сбросить
- `Input` — год от/до
- `ToggleGroup` / `RadioGroup` — выбор типа, статуса просмотра
- `Badge` — отображение активных фильтров

Для мульти-выбора жанров используется **список с чекбоксами** (простой и надёжный, без дополнительных зависимостей). При необходимости замены на комбобокс — миграция тривиальна (заменить список на комбобокс, логика остаётся та же).

### 5.2. Существующие параметры URL

Новые фильтры должны стакаться с существующими:
- `q` (поиск)
- `order` (сортировка)
- `genre` (уже существует, но сейчас один — станет мульти)
- `status` (уже существует)
- `list` (уже существует)
- `page` (пагинация — сбрасывать при смене фильтров)

### 5.3. Бэкенд-совместимость

- Параметр `genre` сейчас принимает одну строку. При переходе на `list[str]` старый формат с одним жанром продолжит работать (Ninja парсит одиночное значение как список из одного элемента).
- Новые параметры (`year_from`, `year_to`, `movie_type`, `watch_status`) — полностью опциональные, без них API ведёт себя как раньше.

### 5.4. Доступность данных для фильтра

Для списка жанров в диалоге нужен отдельный эндпоинт, возвращающий все доступные жанры.

**Решение**: добавить `GET /api/vault/genres` — простой эндпоинт, возвращающий `list[NamedItemOut]`.

```python
@api.get("/genres", response=list[NamedItemOut])
def genre_list(request):
    return [
        NamedItemOut(name=genre.name, slug=genre.slug)
        for genre in Genre.objects.all().order_by("name")
    ]
```

Этот эндпоинт публичный (не требует авторизации), так как список жанров — общедоступные данные.

---

## 6. Что НЕ делаем в этом плане

- Не трогаем модели (`vault/models.py`)
- Не трогаем существующие Django views и templates
- Не меняем структуру `MovieOut` (если не потребуется)
- Не удаляем и не переписываем существующие фильтры (genre, status, list) — расширяем
- Не добавляем пагинацию (уже есть `limit`/`page`)

---

## 7. Чек-лист перед началом реализации

- [ ] План согласован с пользователем
- [ ] Определён формат передачи мульти-жанра: `list[str]` через повторяющиеся query-параметры (`?genre=comedy&genre=action`)
- [ ] Определён UI для мульти-выбора жанров: список с чекбоксами (без внешних зависимостей)
- [ ] Определён источник данных для списка жанров в диалоге: отдельный эндпоинт `GET /api/vault/genres`
- [ ] Определён формат `watch_status` в URL: `watched` / `not_watched` / отсутствие параметра (= «не важно»)
- [ ] Определён формат `is_favorite` в URL: `is_favorite=true` / отсутствие параметра (= «не важно»)
- [ ] Проверены доступные shadcn-svelte компоненты (checkbox, select)