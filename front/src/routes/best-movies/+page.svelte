<script lang="ts">
  import { onDestroy, untrack } from "svelte";
  import { page as pageState } from "$app/state";
  import { pushState, replaceState } from "$app/navigation";
  import { toast } from "svelte-sonner";
  import {
    AlertCircle,
    ArrowDown,
    ArrowUp,
    ExternalLink,
    Film,
    Loader2,
    RefreshCw,
    Star
  } from "@lucide/svelte";
  import { Badge } from "$lib/components/ui/badge";
  import { Button } from "$lib/components/ui/button";
  import * as ButtonGroup from "$lib/components/ui/button-group";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Input } from "$lib/components/ui/input";
  import { Label } from "$lib/components/ui/label";
  import * as Select from "$lib/components/ui/select";
  import { Separator } from "$lib/components/ui/separator";
  import * as Table from "$lib/components/ui/table";
  import {
    PRESET_LABELS,
    WEIGHT_LABELS,
    type BestfilmsofGenreSummary,
    type BestfilmsofMovie,
    type BestfilmsofMovieList,
    type BestfilmsofStatusFilter
  } from "$lib/bestfilmsof";

  type Mode = "list" | "summary";

  type ListQuery = {
    year: string;
    genre: string;
    preset: string;
    customWeights: Record<string, string>;
  };

  type SortKey =
    | "default"
    | "score"
    | "imdb"
    | "votes"
    | "rt"
    | "meta"
    | "gross"
    | "awards"
    | "release"
    | "title";
  type SortDir = "asc" | "desc";

  const PAGE_SIZE = 50;

  const SORT_LABELS: Record<SortKey, string> = {
    default: "По рейтингу сайта",
    score: "Скор bestfilmsof",
    imdb: "IMDb",
    votes: "Голоса IMDb",
    rt: "Rotten Tomatoes",
    meta: "Metascore",
    gross: "Касса",
    awards: "Награды",
    release: "Дата выхода",
    title: "Название"
  };

  const SORT_KEYS = Object.keys(SORT_LABELS) as SortKey[];
  const STATUS_FILTERS: BestfilmsofStatusFilter[] = ["all", "unwatched", "will_watch"];

  function defaultSortDir(key: SortKey): SortDir {
    return key === "title" ? "asc" : "desc";
  }

  let { data } = $props();

  const filters = $derived(data.filters);

  let year = $state("none");
  let genre = $state("all");
  let preset = $state("default");
  let customWeights = $state<Record<string, string>>({
    imdb: "25",
    critics: "25",
    awards: "25",
    boxoffice: "25"
  });

  let result = $state<BestfilmsofMovieList | null>(null);
  let summary = $state<BestfilmsofGenreSummary | null>(null);
  let loading = $state(false);
  let error = $state("");
  let lastUrl = $state<string | null>(null);
  let lastMode = $state<Mode | null>(null);
  let lastYear = $state("none");
  let lastGenre = $state("all");
  let lastQuery = $state<ListQuery | null>(null);
  let statusFilter = $state<BestfilmsofStatusFilter>("all");
  let sortKey = $state<SortKey>("default");
  let sortDir = $state<SortDir>("desc");
  let pageNum = $state(1);
  let appliedPath = "";
  let tableScrollRef = $state<HTMLDivElement | null>(null);
  let sentinelRef = $state<HTMLDivElement | null>(null);
  let loadingGuard = false;

  let pollTimer: ReturnType<typeof setTimeout> | null = null;

  const currentState = $derived(result?.state ?? summary?.state ?? "idle");
  const currentSyncedAt = $derived(result?.synced_at ?? summary?.synced_at ?? null);
  const syncError = $derived(result?.error ?? summary?.error ?? "");
  const isCustom = $derived(preset === "custom");

  function sortValue(movie: BestfilmsofMovie, key: SortKey): number | string | null {
    switch (key) {
      case "score":
        return movie.score;
      case "imdb":
        return movie.imdb_rating;
      case "votes":
        return movie.imdb_votes;
      case "rt":
        return movie.tomato_meter;
      case "meta":
        return movie.metascore;
      case "gross":
        return movie.gross;
      case "awards":
        return movie.award_points;
      case "release":
        return movie.release_date;
      case "title":
        return movieTitle(movie).toLocaleLowerCase("ru");
      default:
        return movie.position;
    }
  }

  const sortedMovies = $derived.by(() => {
    const movies = result?.movies ?? [];
    if (sortKey === "default") return movies;

    const direction = sortDir === "asc" ? 1 : -1;
    return [...movies].sort((left, right) => {
      const leftValue = sortValue(left, sortKey);
      const rightValue = sortValue(right, sortKey);
      if (leftValue == null && rightValue == null) {
        return left.position - right.position;
      }
      if (leftValue == null) return 1;
      if (rightValue == null) return -1;
      if (typeof leftValue === "string" || typeof rightValue === "string") {
        return (
          String(leftValue).localeCompare(String(rightValue), "ru") * direction
        );
      }
      if (leftValue === rightValue) return left.position - right.position;
      return (leftValue - rightValue) * direction;
    });
  });

  const pageCount = $derived(
    Math.max(1, Math.ceil((result?.movies.length ?? 0) / PAGE_SIZE))
  );
  const visibleCount = $derived(
    Math.min(pageNum * PAGE_SIZE, sortedMovies.length)
  );
  const visibleMovies = $derived(sortedMovies.slice(0, visibleCount));
  const hasMore = $derived(visibleCount < sortedMovies.length);

  function clearPoll() {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  onDestroy(clearPoll);

  function currentPath(): string {
    return `${pageState.url.pathname}${pageState.url.search}`;
  }

  function isValidPreset(value: string): boolean {
    return (
      value === "custom" || !!filters?.presets.some((item) => item.name === value)
    );
  }

  function buildPath(): string {
    const params = new URLSearchParams();
    if (year !== "none") params.set("year", year);
    if (genre !== "all") params.set("genre", genre);
    if (preset !== "default") params.set("preset", preset);
    if (preset === "custom") {
      for (const key of ["imdb", "critics", "awards", "boxoffice"]) {
        params.set(`w_${key}`, customWeights[key] || "0");
      }
    }

    if (year !== "none") {
      if (statusFilter !== "all") params.set("status", statusFilter);
      if (sortKey !== "default") {
        params.set("sort", sortKey);
        if (sortDir !== defaultSortDir(sortKey)) params.set("dir", sortDir);
      }
      if (pageNum > 1) params.set("page", String(pageNum));
    }

    const query = params.toString();
    return `/best-movies${query ? `?${query}` : ""}`;
  }

  function commitUrl() {
    const path = buildPath();
    if (path === currentPath()) return;
    // Ставим метку до pushState, чтобы effect не сделал повторный запрос.
    appliedPath = path;
    pushState(path, {});
  }

  function replaceUrlSilently() {
    const path = buildPath();
    if (path === currentPath()) return;
    appliedPath = path;
    replaceState(path, {});
  }

  function scrollTableTop() {
    tableScrollRef?.scrollTo({ top: 0 });
  }

  function showMore() {
    if (!hasMore) {
      loadingGuard = false;
      return;
    }
    restoreLastQueryState();
    pageNum = Math.min(pageNum + 1, pageCount);
    replaceUrlSilently();
    // Даём DOM дорисовать строки, чтобы observer не сработал повторно сразу.
    setTimeout(() => {
      loadingGuard = false;
    }, 120);
  }

  $effect(() => {
    const sentinel = sentinelRef;
    const root = tableScrollRef;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && !loadingGuard && hasMore) {
          loadingGuard = true;
          showMore();
        }
      },
      { root, rootMargin: "200px", threshold: 0.1 }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  });

  function applyUrl(url: URL) {
    const params = url.searchParams;

    const rawYear = params.get("year");
    const validYear =
      !!rawYear &&
      /^\d+$/.test(rawYear) &&
      (filters ? filters.years.includes(Number(rawYear)) : true);
    year = validYear ? rawYear : "none";

    const rawGenre = params.get("genre");
    const validGenre =
      !!rawGenre &&
      (filters ? filters.genres.some((item) => item.slug === rawGenre) : true);
    genre = validGenre ? rawGenre : "all";

    const rawPreset = params.get("preset") ?? "default";
    preset = isValidPreset(rawPreset) ? rawPreset : "default";
    customWeights = {
      imdb: params.get("w_imdb") ?? "25",
      critics: params.get("w_critics") ?? "25",
      awards: params.get("w_awards") ?? "25",
      boxoffice: params.get("w_boxoffice") ?? "25"
    };

    const rawStatus = params.get("status") ?? "all";
    statusFilter = STATUS_FILTERS.includes(rawStatus as BestfilmsofStatusFilter)
      ? (rawStatus as BestfilmsofStatusFilter)
      : "all";

    const rawSort = params.get("sort") ?? "default";
    sortKey = SORT_KEYS.includes(rawSort as SortKey)
      ? (rawSort as SortKey)
      : "default";

    const rawDir = params.get("dir");
    sortDir =
      rawDir === "asc" || rawDir === "desc"
        ? rawDir
        : defaultSortDir(sortKey);

    const parsedPage = Number.parseInt(params.get("page") ?? "1", 10);
    pageNum = Number.isFinite(parsedPage) && parsedPage > 0 ? parsedPage : 1;
  }

  async function loadFromState() {
    clearPoll();
    error = "";

    const hasYear = year !== "none";
    const hasGenre = genre !== "all";
    if (!hasYear && !hasGenre) {
      result = null;
      summary = null;
      lastMode = null;
      lastUrl = null;
      lastQuery = null;
      return;
    }

    lastMode = hasYear ? "list" : "summary";
    lastYear = year;
    lastGenre = genre;

    if (hasYear) {
      summary = null;
      lastQuery = { year, genre, preset, customWeights: { ...customWeights } };
      lastUrl = buildListUrl(lastQuery, statusFilter);
    } else {
      result = null;
      lastQuery = null;
      lastUrl = `/api/bestfilmsof/genres/${encodeURIComponent(genre)}`;
    }

    const state = await fetchData(lastUrl, lastMode);
    scrollTableTop();
    loadingGuard = false;
    if (state === "syncing" || state === "queued") {
      schedulePoll();
    }
  }

  $effect(() => {
    const path = currentPath();
    if (path === appliedPath) return;
    appliedPath = path;
    untrack(() => {
      applyUrl(pageState.url);
      void loadFromState();
    });
  });

  function buildListUrl(query: ListQuery, status: BestfilmsofStatusFilter): string {
    const params = new URLSearchParams({
      year: query.year,
      genre: query.genre === "all" ? "" : query.genre,
      page: "1",
      limit: "500",
      preset: query.preset,
      status_filter: status
    });
    if (query.preset === "custom") {
      for (const key of ["imdb", "critics", "awards", "boxoffice"]) {
        params.set(`w_${key}`, query.customWeights[key] || "0");
      }
    }
    return `/api/bestfilmsof/movies?${params.toString()}`;
  }

  async function fetchData(url: string, mode: Mode, silent = false): Promise<string> {
    if (!silent) loading = true;
    try {
      const response = await fetch(url);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail ?? `Ошибка API: ${response.status}`);
      }
      if (mode === "list") {
        result = payload as BestfilmsofMovieList;
        const maxPage = Math.max(
          1,
          Math.ceil(result.movies.length / PAGE_SIZE)
        );
        if (pageNum > maxPage) {
          pageNum = maxPage;
          replaceUrlSilently();
        }
      } else {
        summary = payload as BestfilmsofGenreSummary;
      }
      error = "";
      return payload.state as string;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
      return "error";
    } finally {
      if (!silent) loading = false;
    }
  }

  function schedulePoll() {
    clearPoll();
    if (!lastUrl || !lastMode) return;
    pollTimer = setTimeout(async () => {
      if (!lastUrl || !lastMode) return;
      const state = await fetchData(lastUrl, lastMode, true);
      if (state === "syncing" || state === "queued") {
        schedulePoll();
      }
    }, 2500);
  }

  async function show() {
    error = "";
    const hasYear = year !== "none";
    const hasGenre = genre !== "all";

    if (!hasYear && !hasGenre) {
      error = "Выберите год и/или жанр.";
      return;
    }

    pageNum = 1;
    commitUrl();
    await loadFromState();
  }

  function restoreLastQueryState() {
    if (!lastQuery) return;
    year = lastQuery.year;
    genre = lastQuery.genre;
    preset = lastQuery.preset;
    customWeights = { ...lastQuery.customWeights };
  }

  async function changeStatusFilter(status: BestfilmsofStatusFilter) {
    if (status === statusFilter) return;
    restoreLastQueryState();
    statusFilter = status;
    pageNum = 1;
    if (lastMode !== "list" || !lastQuery) return;
    commitUrl();
    await loadFromState();
  }

  function changeSort(next: SortKey) {
    restoreLastQueryState();
    sortKey = next;
    sortDir = defaultSortDir(next);
    pageNum = 1;
    commitUrl();
    scrollTableTop();
  }

  function toggleSortDir() {
    if (sortKey === "default") return;
    restoreLastQueryState();
    sortDir = sortDir === "asc" ? "desc" : "asc";
    pageNum = 1;
    commitUrl();
    scrollTableTop();
  }

  async function refresh() {
    if (!lastUrl || !lastMode) return;
    clearPoll();
    const refreshUrl =
      lastMode === "list"
        ? `/api/bestfilmsof/movies/refresh?${new URLSearchParams({
            year: lastYear,
            genre: lastGenre === "all" ? "" : lastGenre
          }).toString()}`
        : `/api/bestfilmsof/genres/${encodeURIComponent(lastGenre)}/refresh`;

    try {
      const response = await fetch(refreshUrl, { method: "POST" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail ?? `Ошибка API: ${response.status}`);
      }
      toast.success("Обновление данных запущено.");
      const state = await fetchData(lastUrl, lastMode, true);
      if (state === "syncing" || state === "queued") {
        schedulePoll();
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  }

  function openYear(value: number) {
    year = String(value);
    if (genre === "all") return;
    void show();
  }

  function formatSynced(value: string | null): string {
    if (!value) return "ещё не синхронизировано";
    return new Date(value).toLocaleString("ru-RU");
  }

  function number(value: number | null): string {
    return value == null ? "—" : new Intl.NumberFormat("ru-RU").format(value);
  }

  function movieTitle(movie: BestfilmsofMovie): string {
    return movie.title_ru || movie.title;
  }

  function posterUrl(path: string | null): string | null {
    return path ? `https://image.tmdb.org/t/p/w185${path}` : null;
  }
</script>

<div class="container mx-auto space-y-6 p-4 md:p-6">
  <div class="flex flex-col justify-between gap-3 md:flex-row md:items-start">
    <div>
      <h1 class="flex items-center gap-2 text-3xl font-extrabold tracking-tight">
        <Film class="h-8 w-8 text-amber-500" />
        BestMovies
      </h1>
      <p class="text-muted-foreground mt-1 max-w-3xl text-sm">
        Рейтинги bestfilmsof.com: фильтр по году и жанру, пресеты весов и локальный
        пересчёт скора. Данные синхронизируются в фоне и потом отдаются из кеша.
      </p>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      {#if currentState === "syncing"}
        <Badge variant="outline" class="gap-1">
          <Loader2 class="h-3 w-3 animate-spin" />
          Синхронизация
        </Badge>
      {:else if currentState === "queued"}
        <Badge variant="outline" class="gap-1">
          <Loader2 class="h-3 w-3 animate-spin" />
          В очереди
        </Badge>
      {:else if currentState === "ready"}
        <Badge variant="secondary">Кеш готов</Badge>
      {:else if currentState === "error"}
        <Badge variant="destructive">Ошибка синка</Badge>
      {/if}
      {#if currentSyncedAt}
        <span class="text-muted-foreground text-xs">Обновлено: {formatSynced(currentSyncedAt)}</span>
      {/if}
    </div>
  </div>

  {#if data.apiError}
    <Card class="border-destructive/50 bg-destructive/5">
      <CardHeader>
        <CardTitle class="flex items-center gap-2 text-destructive">
          <AlertCircle class="h-5 w-5" />
          API недоступен
        </CardTitle>
        <CardDescription>{data.apiError}</CardDescription>
      </CardHeader>
    </Card>
  {:else if filters}
    <Card>
      <CardHeader class="pb-3">
        <CardTitle class="text-lg">Фильтры</CardTitle>
        <CardDescription>
          Год + жанр — полный список. Только жанр — сводка по годам (топ-фильм и количество).
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <div class="grid gap-4 md:grid-cols-3">
          <div class="space-y-2">
            <Label for="best-movies-year">Год</Label>
            <Select.Root type="single" bind:value={year}>
              <Select.Trigger id="best-movies-year" class="w-full">
                {year === "none" ? "—" : year}
              </Select.Trigger>
              <Select.Content>
                <Select.Item value="none">—</Select.Item>
                {#each filters.years as value (value)}
                  <Select.Item value={String(value)}>{value}</Select.Item>
                {/each}
              </Select.Content>
            </Select.Root>
          </div>

          <div class="space-y-2">
            <Label for="best-movies-genre">Жанр</Label>
            <Select.Root type="single" bind:value={genre}>
              <Select.Trigger id="best-movies-genre" class="w-full">
                {genre === "all"
                  ? "все жанры"
                  : (filters.genres.find((item) => item.slug === genre)?.label ?? genre)}
              </Select.Trigger>
              <Select.Content>
                <Select.Item value="all">все жанры</Select.Item>
                {#each filters.genres as item (item.slug)}
                  <Select.Item value={item.slug}>{item.label}</Select.Item>
                {/each}
              </Select.Content>
            </Select.Root>
          </div>

          <div class="space-y-2">
            <Label for="best-movies-preset">Веса</Label>
            <Select.Root type="single" bind:value={preset}>
              <Select.Trigger id="best-movies-preset" class="w-full">
                {PRESET_LABELS[preset] ?? preset}
              </Select.Trigger>
              <Select.Content>
                {#each filters.presets as item (item.name)}
                  <Select.Item value={item.name}>{PRESET_LABELS[item.name] ?? item.name}</Select.Item>
                {/each}
                <Select.Item value="custom">{PRESET_LABELS.custom}</Select.Item>
              </Select.Content>
            </Select.Root>
          </div>
        </div>

        {#if isCustom}
          <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {#each filters.weight_keys as key (key)}
              <div class="space-y-2">
                <Label for={`best-movies-weight-${key}`}>{WEIGHT_LABELS[key] ?? key}</Label>
                <Input
                  id={`best-movies-weight-${key}`}
                  type="number"
                  min="0"
                  max="100"
                  bind:value={customWeights[key]}
                />
              </div>
            {/each}
          </div>
        {/if}

        <div class="flex flex-wrap items-center gap-2">
          <Button onclick={show} disabled={loading}>
            {#if loading}
              <Loader2 class="mr-2 h-4 w-4 animate-spin" />
            {:else}
              <Star class="mr-2 h-4 w-4" />
            {/if}
            Показать
          </Button>
          <Button variant="outline" onclick={refresh} disabled={!lastUrl || currentState === "syncing"}>
            <RefreshCw class="mr-2 h-4 w-4" />
            Обновить данные
          </Button>
        </div>

        {#if error}
          <p class="text-destructive text-sm font-medium">{error}</p>
        {/if}
      </CardContent>
    </Card>

    {#if syncError}
      <Card class="border-destructive/50 bg-destructive/5">
        <CardContent class="flex items-start gap-2 pt-6 text-sm">
          <AlertCircle class="text-destructive mt-0.5 h-4 w-4 shrink-0" />
          <span>Синхронизация завершилась ошибкой: {syncError}</span>
        </CardContent>
      </Card>
    {/if}

    {#if loading && !result && !summary}
      <Card>
        <CardContent class="flex items-center gap-3 py-10">
          <Loader2 class="text-muted-foreground h-5 w-5 animate-spin" />
          <span class="text-muted-foreground text-sm">Загружаем данные…</span>
        </CardContent>
      </Card>
    {:else if result}
      <Card>
        <CardHeader class="pb-3">
          <div class="flex flex-col justify-between gap-2 md:flex-row md:items-center">
            <div>
              <CardTitle class="text-lg">
                {result.year} / {result.genre || "все жанры"}
                <span class="text-muted-foreground ml-2 text-sm font-normal">{result.total} фильмов</span>
              </CardTitle>
              <CardDescription>
                {#if result.weights}
                  Локальный пересчёт:
                  {Object.entries(result.weights)
                    .filter(([, value]) => value > 0)
                    .map(([key, value]) => `${WEIGHT_LABELS[key] ?? key} ${value}`)
                    .join(" · ")}
                {:else}
                  Сортировка сайта по умолчанию
                {/if}
              </CardDescription>
            </div>
            {#if result.is_stale}
              <Badge variant="outline">Кеш устарел — обновится в фоне</Badge>
            {/if}
          </div>
        </CardHeader>
        <CardContent>
          <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
            <ButtonGroup.Root>
              <Button
                size="sm"
                variant={statusFilter === "all" ? "secondary" : "outline"}
                aria-pressed={statusFilter === "all"}
                onclick={() => changeStatusFilter("all")}
                disabled={loading}
              >
                Все фильмы
                <span class="text-muted-foreground ml-1 text-xs">{result.counts.all}</span>
              </Button>
              <Button
                size="sm"
                variant={statusFilter === "unwatched" ? "secondary" : "outline"}
                aria-pressed={statusFilter === "unwatched"}
                onclick={() => changeStatusFilter("unwatched")}
                disabled={loading}
              >
                Непросмотренные
                <span class="text-muted-foreground ml-1 text-xs">{result.counts.unwatched}</span>
              </Button>
              <Button
                size="sm"
                variant={statusFilter === "will_watch" ? "secondary" : "outline"}
                aria-pressed={statusFilter === "will_watch"}
                title="Непросмотренные фильмы со статусом «Буду смотреть»"
                onclick={() => changeStatusFilter("will_watch")}
                disabled={loading}
              >
                Буду смотреть
                <span class="text-muted-foreground ml-1 text-xs">{result.counts.will_watch}</span>
              </Button>
            </ButtonGroup.Root>

            <div class="flex items-center gap-2">
              <span class="text-muted-foreground text-xs">Сортировка</span>
              <Select.Root
                type="single"
                value={sortKey}
                onValueChange={(value) => {
                  if (value) changeSort(value as SortKey);
                }}
              >
                <Select.Trigger class="w-48">
                  {SORT_LABELS[sortKey]}
                </Select.Trigger>
                <Select.Content>
                  {#each SORT_KEYS as key (key)}
                    <Select.Item value={key}>{SORT_LABELS[key]}</Select.Item>
                  {/each}
                </Select.Content>
              </Select.Root>
              <Button
                variant="outline"
                size="icon"
                onclick={toggleSortDir}
                disabled={sortKey === "default"}
                title={sortDir === "asc" ? "По возрастанию" : "По убыванию"}
              >
                {#if sortDir === "asc"}
                  <ArrowUp class="h-4 w-4" />
                {:else}
                  <ArrowDown class="h-4 w-4" />
                {/if}
              </Button>
            </div>
          </div>

          <div class="text-muted-foreground mb-2 flex flex-wrap items-center justify-between gap-2 text-xs">
            <span>
              Показано: {visibleCount} из {result.total}
              {#if statusFilter !== "all"}
                (всего в списке {result.counts.all})
              {/if}
            </span>
            {#if hasMore}
              <span>Прокрутите таблицу, чтобы подгрузить ещё</span>
            {/if}
          </div>

          {#if (result.state === "syncing" || result.state === "queued") && result.total === 0}
            <div class="text-muted-foreground flex items-center gap-3 py-10 text-sm">
              <Loader2 class="h-5 w-5 animate-spin" />
              {#if result.state === "queued"}
                <span>
                  Задача в очереди. Если статус не меняется, проверь, что Huey-воркер
                  запущен и перезапущен после обновления кода.
                </span>
              {:else}
                <span>
                  Тянем список с bestfilmsof.com. Первый заход может занять до минуты;
                  страница обновится сама.
                </span>
              {/if}
            </div>
          {:else if result.movies.length === 0}
            <p class="text-muted-foreground py-8 text-sm">
              {#if result.counts.all > 0 && statusFilter !== "all"}
                Под выбранный фильтр статусов ничего не попало. В списке всего {result.counts.all} фильмов.
              {:else}
                Для этой пары год + жанр на bestfilmsof.com нет фильмов.
              {/if}
            </p>
          {:else}
            <div bind:this={tableScrollRef} class="max-h-[70vh] overflow-auto rounded-lg border">
              <table class="w-full caption-bottom text-sm">
                <Table.Header class="[&_th]:bg-card [&_th]:sticky [&_th]:top-0 [&_th]:z-10">
                  <Table.Row>
                    <Table.Head class="w-12" title="Позиция в рейтинге bestfilmsof"># сайта</Table.Head>
                    <Table.Head class="w-16">Постер</Table.Head>
                    <Table.Head>Фильм</Table.Head>
                    <Table.Head class="w-20 text-right">Скор</Table.Head>
                    <Table.Head class="w-24 text-right">IMDb</Table.Head>
                    <Table.Head class="w-24 text-right">RT / Meta</Table.Head>
                    <Table.Head class="w-28 text-right">Награды</Table.Head>
                    <Table.Head class="w-20" />
                  </Table.Row>
                </Table.Header>
                <Table.Body>
                  {#each visibleMovies as movie (movie.imdb_id)}
                    {@const poster = posterUrl(movie.poster_path)}
                    <Table.Row>
                      <Table.Cell class="text-muted-foreground font-mono text-xs">{movie.position}</Table.Cell>
                      <Table.Cell>
                        {#if poster}
                          <img
                            src={poster}
                            alt=""
                            loading="lazy"
                            class="h-16 w-11 rounded object-cover"
                          />
                        {/if}
                      </Table.Cell>
                      <Table.Cell>
                        <div class="font-medium">{movieTitle(movie)}</div>
                        {#if movie.title_ru && movie.title !== movie.title_ru}
                          <div class="text-muted-foreground text-xs">{movie.title}</div>
                        {/if}
                        {#if movie.watch_status || movie.in_favorites || movie.rating != null}
                          <div class="mt-1 flex flex-wrap items-center gap-1">
                            {#if movie.watch_status === "watched"}
                              <Badge variant="secondary">Просмотрено</Badge>
                            {:else if movie.watch_status === "will_watch"}
                              <Badge variant="outline">Буду смотреть</Badge>
                            {:else if movie.watch_status === "wont_watch"}
                              <Badge variant="outline">Не интересует</Badge>
                            {/if}
                            {#if movie.in_favorites}
                              <Badge variant="outline">★ Избранное</Badge>
                            {/if}
                            {#if movie.rating != null}
                              <Badge variant="outline">Оценка {movie.rating}</Badge>
                            {/if}
                          </div>
                        {/if}
                        {#if movie.overview_ru || movie.overview}
                          <p class="text-muted-foreground mt-1 line-clamp-2 max-w-xl text-xs">
                            {movie.overview_ru || movie.overview}
                          </p>
                        {/if}
                      </Table.Cell>
                      <Table.Cell class="text-right font-semibold">
                        {movie.score == null ? "—" : movie.score.toFixed(2)}
                      </Table.Cell>
                      <Table.Cell class="text-right">
                        {movie.imdb_rating == null ? "—" : movie.imdb_rating.toFixed(1)}
                        {#if movie.imdb_votes}
                          <div class="text-muted-foreground text-xs">{number(movie.imdb_votes)}</div>
                        {/if}
                      </Table.Cell>
                      <Table.Cell class="text-right">
                        {movie.tomato_meter == null ? "—" : movie.tomato_meter}
                        /
                        {movie.metascore == null ? "—" : movie.metascore}
                      </Table.Cell>
                      <Table.Cell class="text-right text-xs">
                        {movie.oscar_wins}W / {movie.oscar_nominations}N
                        {#if movie.best_picture}
                          <div class="text-amber-600 dark:text-amber-400">Best Picture</div>
                        {/if}
                      </Table.Cell>
                      <Table.Cell>
                        {#if movie.in_collection && movie.collection_slug}
                          <a href={`/movies/${movie.collection_slug}`}>
                            <Badge variant="secondary" class="gap-1">
                              <ExternalLink class="h-3 w-3" />
                              Vault
                            </Badge>
                          </a>
                        {/if}
                      </Table.Cell>
                    </Table.Row>
                  {/each}
                </Table.Body>
              </table>
              <div bind:this={sentinelRef} class="flex h-12 items-center justify-center">
                {#if hasMore}
                  <span class="text-muted-foreground flex items-center gap-2 text-xs">
                    <Loader2 class="h-4 w-4 animate-spin" />
                    Загружаем ещё…
                  </span>
                {:else}
                  <span class="text-muted-foreground text-xs">Это все фильмы</span>
                {/if}
              </div>
            </div>
          {/if}
        </CardContent>
      </Card>
    {:else if summary}
      <Card>
        <CardHeader class="pb-3">
          <div class="flex flex-col justify-between gap-2 md:flex-row md:items-center">
            <div>
              <CardTitle class="text-lg">
                Жанр: {filters.genres.find((item) => item.slug === summary?.genre)?.label ?? summary.genre}
                <span class="text-muted-foreground ml-2 text-sm font-normal">{summary.total} лет</span>
              </CardTitle>
              <CardDescription>Топ-фильм и количество фильмов по годам</CardDescription>
            </div>
            {#if summary.is_stale}
              <Badge variant="outline">Кеш устарел — обновится в фоне</Badge>
            {/if}
          </div>
        </CardHeader>
        <CardContent>
          {#if (summary.state === "syncing" || summary.state === "queued") && summary.total === 0}
            <div class="text-muted-foreground flex items-center gap-3 py-10 text-sm">
              <Loader2 class="h-5 w-5 animate-spin" />
              {#if summary.state === "queued"}
                <span>
                  Задача в очереди. Если статус не меняется, проверь, что Huey-воркер
                  запущен и перезапущен после обновления кода.
                </span>
              {:else}
                <span>Загружаем сводку по жанру…</span>
              {/if}
            </div>
          {:else if summary.years.length === 0}
            <p class="text-muted-foreground py-8 text-sm">Нет данных для этого жанра.</p>
          {:else}
            <div class="overflow-x-auto rounded-lg border">
              <Table.Root>
                <Table.Header>
                  <Table.Row>
                    <Table.Head class="w-20">Год</Table.Head>
                    <Table.Head class="w-20 text-right">Фильмов</Table.Head>
                    <Table.Head class="w-16">Постер</Table.Head>
                    <Table.Head>Топ-фильм</Table.Head>
                    <Table.Head class="w-20 text-right">Скор</Table.Head>
                    <Table.Head class="w-20" />
                  </Table.Row>
                </Table.Header>
                <Table.Body>
                  {#each summary.years as item (item.year)}
                    {@const poster = posterUrl(item.top_poster_path)}
                    <Table.Row>
                      <Table.Cell>
                        <button class="font-medium underline-offset-4 hover:underline" onclick={() => openYear(item.year)}>
                          {item.year}
                        </button>
                      </Table.Cell>
                      <Table.Cell class="text-right">{item.count}</Table.Cell>
                      <Table.Cell>
                        {#if poster}
                          <img src={poster} alt="" loading="lazy" class="h-16 w-11 rounded object-cover" />
                        {/if}
                      </Table.Cell>
                      <Table.Cell>
                        <div class="font-medium">{item.top_title_ru || item.top_title}</div>
                        {#if item.top_overview_ru}
                          <p class="text-muted-foreground mt-1 line-clamp-2 max-w-xl text-xs">
                            {item.top_overview_ru}
                          </p>
                        {/if}
                      </Table.Cell>
                      <Table.Cell class="text-right font-semibold">
                        {item.top_score == null ? "—" : item.top_score.toFixed(2)}
                      </Table.Cell>
                      <Table.Cell>
                        {#if item.in_collection && item.collection_slug}
                          <a href={`/movies/${item.collection_slug}`}>
                            <Badge variant="secondary" class="gap-1">
                              <ExternalLink class="h-3 w-3" />
                              Vault
                            </Badge>
                          </a>
                        {/if}
                      </Table.Cell>
                    </Table.Row>
                  {/each}
                </Table.Body>
              </Table.Root>
            </div>
          {/if}
        </CardContent>
      </Card>
    {/if}
  {/if}

  <Separator />
  <p class="text-muted-foreground text-xs">
    Источник рейтингов: bestfilmsof.com. Постеры, названия и описания — TMDB / коллекция Vault.
  </p>
</div>
