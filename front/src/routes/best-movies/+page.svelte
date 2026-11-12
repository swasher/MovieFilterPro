<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { afterNavigate, goto, replaceState } from "$app/navigation";
  import { toast } from "svelte-sonner";
  import {
    AlertCircle,
    ArrowDown,
    ArrowUp,
    CircleHelp,
    ExternalLink,
    Film,
    LayoutGrid,
    Loader2,
    PanelRightClose,
    PanelRightOpen,
    RefreshCw,
    TextAlignJustify
  } from "@lucide/svelte";
  import { Badge } from "$lib/components/ui/badge";
  import { Button } from "$lib/components/ui/button";
  import * as ButtonGroup from "$lib/components/ui/button-group";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Label } from "$lib/components/ui/label";
  import * as Popover from "$lib/components/ui/popover";
  import * as Select from "$lib/components/ui/select";
  import { Slider } from "$lib/components/ui/slider";
  import { Switch } from "$lib/components/ui/switch";
  import * as Table from "$lib/components/ui/table";
  import * as ToggleGroup from "$lib/components/ui/toggle-group";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import VaultImage from "$lib/components/vault/VaultImage.svelte";
  import MovieStatusBadges from "$lib/components/vault/MovieStatusBadges.svelte";
  import {
    WEIGHT_LABELS,
    type BestfilmsofGenreSummary,
    type BestfilmsofMovie,
    type BestfilmsofMovieList,
    type BestfilmsofStatusFilter
  } from "$lib/bestfilmsof";
  import { normalizeWeights, redistributeWeights } from "$lib/weights";

  type Mode = "list" | "summary";

  type ListQuery = {
    year: string;
    genre: string;
    preset: string;
    customWeights: Record<string, number>;
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
  // Сколько последних лет показывать сразу в toggle group; остальные — под «…».
  const YEAR_QUICK_LIMIT = 16;

  const SORT_LABELS: Record<SortKey, string> = {
    default: "По формуле",
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

  // Короткие подписи пресетов для чипов в блоке весов.
  const PRESET_CHIP_LABELS: Record<string, string> = {
    default: "Defaults",
    critics: "Выбор критиков",
    crowd: "Выбор зрителей",
    awards: "Награды",
    "no-boxoffice": "Без учета кассы"
  };
  // Во сколько включается компонент, если у него ещё не было ненулевого веса.
  const DEFAULT_WEIGHT = 25;
  const WEIGHT_FALLBACK_KEYS = ["imdb", "critics", "awards", "boxoffice"];
  const WEIGHTS_VISIBLE_KEY = "best-movies:weights-visible";

  function defaultSortDir(key: SortKey): SortDir {
    return key === "title" ? "asc" : "desc";
  }

  let { data } = $props();

  const filters = $derived(data.filters);

  let year = $state("none");
  let genre = $state("all");
  let yearMenuOpen = $state(false);
  let preset = $state("default");
  // Панель «Формула рейтинга» можно скрыть; выбор запоминаем между заходами.
  let weightsVisible = $state(readWeightsVisible());
  // Сумма весов всегда 100: стартовые значения совпадают с пресетом Defaults,
  // а applyUrl/выбор пресета сразу подставят актуальные.
  let customWeights = $state<Record<string, number>>({
    imdb: 30,
    critics: 30,
    awards: 20,
    boxoffice: 20
  });
  // Последние ненулевые веса — чтобы switch возвращал компонент, а не включал с нуля.
  let lastWeights = $state<Record<string, number>>({
    imdb: DEFAULT_WEIGHT,
    critics: DEFAULT_WEIGHT,
    awards: DEFAULT_WEIGHT,
    boxoffice: DEFAULT_WEIGHT
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
  let isListView = $state(false);
  let sentinelRef = $state<HTMLDivElement | null>(null);
  let loadingGuard = false;
  // Защита от гонок: применяем только ответ на последний запрос.
  let fetchSeq = 0;

  let pollTimer: ReturnType<typeof setTimeout> | null = null;

  const currentState = $derived(result?.state ?? summary?.state ?? "idle");
  const currentSyncedAt = $derived(result?.synced_at ?? summary?.synced_at ?? null);
  const syncError = $derived(result?.error ?? summary?.error ?? "");

  const weightKeys = $derived(filters?.weight_keys ?? WEIGHT_FALLBACK_KEYS);

  const quickYears = $derived(
    (filters?.years ?? []).slice(0, YEAR_QUICK_LIMIT)
  );
  // Значение года по умолчанию: при входе на страницу всегда показываем последний год.
  const latestYear = $derived(
    filters?.years?.length ? String(filters.years[0]) : "none"
  );
  const moreYears = $derived((filters?.years ?? []).slice(YEAR_QUICK_LIMIT));
  // Старые годы разбиваем по десятилетиям: так проще ориентироваться в длинном списке.
  const moreYearGroups = $derived.by(() => {
    const groups: { key: string; label: string; years: number[] }[] = [];
    for (const value of moreYears) {
      const decade = Math.floor(value / 10) * 10;
      const key = String(decade);
      let group = groups.at(-1);
      if (!group || group.key !== key) {
        group = { key, label: `${decade}-е`, years: [] };
        groups.push(group);
      }
      group.years.push(value);
    }
    return groups;
  });
  // Выбранный «старый» год показываем на самой кнопке «…», чтобы выбор не терялся.
  const hiddenYear = $derived(
    year !== "none" && !quickYears.includes(Number(year)) ? year : null
  );

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
    if (typeof window === "undefined") return "";
    return `${window.location.pathname}${window.location.search}`;
  }

  function isValidPreset(value: string): boolean {
    return (
      value === "custom" || !!filters?.presets.some((item) => item.name === value)
    );
  }

  function buildPath(): string {
    const params = new URLSearchParams();
    // Год пишем всегда: отсутствие параметра означает «вход на страницу»
    // и подставляет последний год, а year=none — режим сводки по жанру.
    params.set("year", year);
    if (genre !== "all") params.set("genre", genre);
    if (preset !== "default") params.set("preset", preset);
    if (preset === "custom") {
      for (const key of ["imdb", "critics", "awards", "boxoffice"]) {
        params.set(`w_${key}`, String(customWeights[key] ?? 0));
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
    // Обычная навигация SvelteKit: URL, page.url и история остаются согласованными.
    // Shallow pushState здесь использовать нельзя — он не обновляет page.url и
    // ломает load при возврате назад (SvelteKit issue #13569/#11465).
    void goto(path, { noScroll: true, keepFocus: true }).catch((err) => {
      const message = err instanceof Error ? err.message : String(err);
      // Быстрые клики по фильтрам отменяют предыдущую навигацию — это не ошибка.
      if (message === "navigation aborted" || message === "navigation cancelled") return;
      error = message;
    });
  }

  function replaceUrlSilently() {
    const path = buildPath();
    if (path === currentPath()) return;
    // Только прогресс infinite scroll: без навигации и без перезапуска load.
    void replaceState(path, {});
  }

  function scrollTableTop() {
    window.scrollTo({ top: 0, behavior: "auto" });
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
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && !loadingGuard && hasMore) {
          loadingGuard = true;
          showMore();
        }
      },
      { rootMargin: "200px", threshold: 0.1 }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  });

  function applyUrl(url: URL): boolean {
    const params = url.searchParams;
    const previous = {
      year,
      genre,
      preset,
      status: statusFilter,
      weights: JSON.stringify(customWeights)
    };

    const rawYear = params.get("year");
    const validYear =
      !!rawYear &&
      /^\d+$/.test(rawYear) &&
      (filters ? filters.years.includes(Number(rawYear)) : true);
    // Нет параметра или он битый — показываем последний год (дефолт при входе).
    year = rawYear === "none" ? "none" : validYear && rawYear ? rawYear : latestYear;

    const rawGenre = params.get("genre");
    const validGenre =
      !!rawGenre &&
      (filters ? filters.genres.some((item) => item.slug === rawGenre) : true);
    genre = validGenre ? rawGenre : "all";

    const rawPreset = params.get("preset") ?? "default";
    preset = isValidPreset(rawPreset) ? rawPreset : "default";
    if (preset === "custom") {
      const parsed = Object.fromEntries(
        weightKeys.map((key) => [key, parseWeight(params.get(`w_${key}`))])
      );
      customWeights = normalizeWeights(parsed, weightKeys, weightsForPreset("default"));
    } else {
      // Для именованных пресетов слайдеры показывают именно их веса (сумма 100).
      customWeights = normalizedPresetWeights(preset);
    }
    rememberWeights();

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

    // Панель формулы открыта → сортировка всегда по формуле, что бы ни было в URL.
    if (weightsVisible) {
      sortKey = "default";
      sortDir = defaultSortDir("default");
    }

    const parsedPage = Number.parseInt(params.get("page") ?? "1", 10);
    pageNum = Number.isFinite(parsedPage) && parsedPage > 0 ? parsedPage : 1;

    return (
      previous.year !== year ||
      previous.genre !== genre ||
      previous.preset !== preset ||
      previous.status !== statusFilter ||
      (preset === "custom" && previous.weights !== JSON.stringify(customWeights))
    );
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
    loadingGuard = false;
    if (state === "syncing" || state === "queued") {
      schedulePoll();
    }
  }

  function syncFromLocation() {
    if (window.location.pathname !== "/best-movies") return;
    const changed = applyUrl(new URL(window.location.href));
    if (changed) {
      void loadFromState();
      return;
    }
    // Первый заход: в URL параметров ещё нет, показываем дефолт
    // (последний год + все жанры).
    if (!lastUrl && !loading) void loadFromState();
  }

  onMount(() => {
    syncFromLocation();
    window.addEventListener("popstate", syncFromLocation);
    return () => window.removeEventListener("popstate", syncFromLocation);
  });

  afterNavigate(() => {
    syncFromLocation();
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
        params.set(`w_${key}`, String(query.customWeights[key] ?? 0));
      }
    }
    return `/api/bestfilmsof/movies?${params.toString()}`;
  }

  async function fetchData(url: string, mode: Mode, silent = false): Promise<string> {
    const seq = ++fetchSeq;
    if (!silent) loading = true;
    try {
      const response = await fetch(url);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail ?? `Ошибка API: ${response.status}`);
      }
      // Пока шёл запрос, пользователь мог выбрать другой год/жанр — этот ответ уже не нужен.
      if (seq !== fetchSeq) return "stale";
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
      if (seq === fetchSeq) {
        error = err instanceof Error ? err.message : String(err);
      }
      return "error";
    } finally {
      if (!silent && seq === fetchSeq) loading = false;
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

  async function applyFilters() {
    pageNum = 1;
    commitUrl();
    await loadFromState();
    scrollTableTop();
  }

  async function changeYear(value: string | undefined) {
    const next = value || "none";
    if (next === year) return;
    year = next;
    await applyFilters();
  }

  async function changeGenre(value: string | undefined) {
    const next = value || "all";
    if (next === genre) return;
    genre = next;
    // В сводке по жанру год не выбран: если жанр сброшен, возвращаемся
    // к дефолтному виду «последний год + все жанры».
    if (next === "all" && year === "none") year = latestYear;
    await applyFilters();
  }

  async function changePresetWeight(name: string) {
    if (name === preset) return;
    preset = name;
    applyPresetWeights(name);
    await applyFilters();
  }

  function onPresetKeydown(event: KeyboardEvent, name: string) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    void changePresetWeight(name);
  }

  function toggleWeights() {
    weightsVisible = !weightsVisible;
    // Пока панель открыта, сортировка возможна только по формуле рейтинга.
    if (weightsVisible && sortKey !== "default") {
      sortKey = "default";
      sortDir = defaultSortDir("default");
      pageNum = 1;
      commitUrl();
    }
    try {
      localStorage.setItem(WEIGHTS_VISIBLE_KEY, weightsVisible ? "1" : "0");
    } catch {
      // localStorage недоступен — просто переключаем панель.
    }
  }

  function readWeightsVisible(): boolean {
    try {
      return localStorage.getItem(WEIGHTS_VISIBLE_KEY) !== "0";
    } catch {
      return true;
    }
  }

  async function resetWeights() {
    if (preset === "default") return;
    preset = "default";
    applyPresetWeights("default");
    await applyFilters();
  }

  function parseWeight(value: string | null): number {
    const parsed = Number.parseInt(value ?? "", 10);
    if (!Number.isFinite(parsed)) return 0;
    return Math.max(0, Math.min(100, parsed));
  }

  function weightsForPreset(name: string): Record<string, number> {
    const presetWeights = filters?.presets.find((item) => item.name === name)?.weights;
    return Object.fromEntries(
      weightKeys.map((key) => [key, presetWeights?.[key] ?? 0])
    );
  }

  function applyPresetWeights(name: string) {
    customWeights = normalizedPresetWeights(name);
    rememberWeights();
  }

  function normalizedPresetWeights(name: string): Record<string, number> {
    return normalizeWeights(
      weightsForPreset(name),
      weightKeys,
      weightsForPreset("default")
    );
  }

  function rememberWeights() {
    for (const key of weightKeys) {
      const value = customWeights[key] ?? 0;
      if (value > 0) lastWeights[key] = value;
    }
  }

  function onWeightChange(key: string, value: number) {
    const next = redistributeWeights(customWeights, key, value);
    const changed = weightKeys.some(
      (item) => (next[item] ?? 0) !== (customWeights[item] ?? 0)
    );
    if (!changed) return;
    customWeights = next;
    const own = next[key] ?? 0;
    if (own > 0) lastWeights[key] = own;
    // Любая ручная правка слайдера означает свои веса.
    if (preset !== "custom") preset = "custom";
  }

  async function toggleWeight(key: string, enabled: boolean) {
    const target = enabled ? lastWeights[key] || DEFAULT_WEIGHT : 0;
    if ((customWeights[key] ?? 0) === target && preset === "custom") return;
    onWeightChange(key, target);
    if (preset !== "custom") preset = "custom";
    await applyFilters();
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
    scrollTableTop();
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

  async function openYear(value: number) {
    const next = String(value);
    if (next === year) return;
    year = next;
    await applyFilters();
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

  function posterUrl(path: string | null, size: "w185" | "w342" = "w185"): string | null {
    return path ? `https://image.tmdb.org/t/p/${size}${path}` : null;
  }
</script>

<div class="container mx-auto space-y-6 p-4 md:p-6">
  <div class="flex flex-col justify-between gap-3 md:flex-row md:items-start">
    <div>
      <h1 class="flex items-center gap-2 text-3xl font-extrabold tracking-tight">
        <Film class="h-8 w-8 text-amber-500" />
        BestMovies
      </h1>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      {#if loading}
        <Badge variant="outline" class="gap-1">
          <Loader2 class="h-3 w-3 animate-spin" />
          Загрузка
        </Badge>
      {/if}
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
      <Button
        variant="outline"
        size="sm"
        onclick={refresh}
        disabled={!lastUrl || currentState === "syncing"}
      >
        <RefreshCw class="mr-2 h-4 w-4" />
        Обновить данные
      </Button>
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
    <div
      class={`grid gap-4 lg:items-stretch lg:gap-3 lg:transition-[grid-template-columns] lg:duration-300 lg:ease-out ${
        weightsVisible
          ? "lg:grid-cols-[minmax(0,1fr)_auto_20rem]"
          : "lg:grid-cols-[minmax(0,1fr)_auto_0rem]"
      }`}
    >
      <Card>
        <CardContent class="space-y-4">
          <div class="space-y-2">
            <Label>Год</Label>
            <div class="flex flex-wrap items-start gap-2">
              <ToggleGroup.Root
                type="single"
                size="sm"
                variant="outline"
                spacing={2}
                value={year === "none" ? "" : year}
                onValueChange={changeYear}
                class="flex-wrap"
              >
                <ToggleGroup.Item value="">—</ToggleGroup.Item>
                {#each quickYears as value (value)}
                  <ToggleGroup.Item value={String(value)}>{value}</ToggleGroup.Item>
                {/each}
              </ToggleGroup.Root>

              {#if moreYears.length > 0}
                <Popover.Root bind:open={yearMenuOpen}>
                  <Popover.Trigger>
                    {#snippet child({ props })}
                      <Button
                        {...props}
                        size="sm"
                        variant={hiddenYear ? "secondary" : "outline"}
                        class="h-8 px-2.5"
                        aria-label="Ещё годы"
                        title="Ещё годы"
                      >
                        {hiddenYear ?? "…"}
                      </Button>
                    {/snippet}
                  </Popover.Trigger>
                  <Popover.Content class="w-72" align="start">
                    <div class="max-h-64 space-y-2 overflow-y-auto pr-1">
                      {#each moreYearGroups as group (group.key)}
                        <div class="space-y-1">
                          <div class="text-muted-foreground bg-popover sticky top-0 text-xs">
                            {group.label}
                          </div>
                          <ToggleGroup.Root
                            type="single"
                            size="sm"
                            variant="outline"
                            spacing={2}
                            value={year}
                            class="flex-wrap"
                            onValueChange={(value) => {
                              yearMenuOpen = false;
                              void changeYear(value);
                            }}
                          >
                            {#each group.years as value (value)}
                              <ToggleGroup.Item value={String(value)}>{value}</ToggleGroup.Item>
                            {/each}
                          </ToggleGroup.Root>
                        </div>
                      {/each}
                    </div>
                  </Popover.Content>
                </Popover.Root>
              {/if}
            </div>
          </div>

          <div class="space-y-2">
            <Label>Жанр</Label>
            <ToggleGroup.Root
              type="single"
              size="sm"
              variant="outline"
              spacing={2}
              value={genre === "all" ? "" : genre}
              onValueChange={changeGenre}
              class="flex-wrap"
            >
              <ToggleGroup.Item value="">все жанры</ToggleGroup.Item>
              {#each filters.genres as item (item.slug)}
                <ToggleGroup.Item value={item.slug}>{item.label}</ToggleGroup.Item>
              {/each}
            </ToggleGroup.Root>
          </div>

          {#if error}
            <p class="text-destructive text-sm font-medium">{error}</p>
          {/if}
        </CardContent>
      </Card>

      <div class="flex items-center justify-center">
        <Button
          variant="outline"
          size="icon"
          class="h-8 w-8 rounded-full"
          onclick={toggleWeights}
          aria-expanded={weightsVisible}
          aria-controls="best-movies-weights"
          aria-label={weightsVisible ? "Скрыть формулу рейтинга" : "Показать формулу рейтинга"}
          title={weightsVisible ? "Скрыть формулу рейтинга" : "Показать формулу рейтинга"}
        >
          {#if weightsVisible}
            <PanelRightClose class="h-4 w-4" />
          {:else}
            <PanelRightOpen class="h-4 w-4" />
          {/if}
        </Button>
      </div>

      <Card
        id="best-movies-weights"
        class={`min-w-0 overflow-hidden transition-opacity duration-300 ${
          weightsVisible ? "opacity-100" : "pointer-events-none opacity-0 max-lg:hidden"
        }`}
        inert={!weightsVisible}
      >
        <CardContent class="flex w-full flex-1 flex-col gap-4 lg:w-80">
          <div class="flex items-center gap-1.5">
            <div class="text-sm font-semibold">Формула рейтинга</div>
            <Tooltip.Provider>
              <Tooltip.Root>
                <Tooltip.Trigger>
                  {#snippet child({ props })}
                    <button
                      {...props}
                      type="button"
                      class="text-muted-foreground hover:text-foreground inline-flex"
                      aria-label="Как считаются веса"
                    >
                      <CircleHelp class="size-4" />
                    </button>
                  {/snippet}
                </Tooltip.Trigger>
                <Tooltip.Content side="bottom" align="start" class="max-w-64">
                  Фильмы сравниваются внутри своего года. Настройки сохраняются в ссылке.
                </Tooltip.Content>
              </Tooltip.Root>
            </Tooltip.Provider>
            <button
              type="button"
              class="text-muted-foreground hover:text-foreground ml-auto text-xs underline-offset-4 hover:underline disabled:pointer-events-none disabled:opacity-40"
              onclick={resetWeights}
              disabled={preset === "default"}
            >
              reset
            </button>
          </div>

          <div class="-mx-1.5 flex flex-wrap gap-1">
            {#each filters.presets as item (item.name)}
              {@const active = preset === item.name}
              <Label
                role="button"
                tabindex={0}
                aria-pressed={active}
                class={`cursor-pointer rounded-md px-1.5 py-0.5 text-xs transition-colors ${
                  active
                    ? "bg-secondary text-secondary-foreground"
                    : "text-muted-foreground hover:bg-muted"
                }`}
                onclick={() => void changePresetWeight(item.name)}
                onkeydown={(event) => onPresetKeydown(event, item.name)}
              >
                {PRESET_CHIP_LABELS[item.name] ?? item.name}
              </Label>
            {/each}
          </div>

          <div class="space-y-3">
            {#each filters.weight_keys as key (key)}
              <div class="space-y-1.5">
                <div class="flex items-center justify-between gap-3">
                  <span class="text-sm font-medium">{WEIGHT_LABELS[key] ?? key}</span>
                  <div class="flex items-center gap-2">
                    <span class="text-muted-foreground w-8 text-right text-xs tabular-nums">
                      {customWeights[key] ? `${customWeights[key]}%` : "off"}
                    </span>
                    <Switch
                      size="sm"
                      checked={(customWeights[key] ?? 0) > 0}
                      onCheckedChange={(checked) => toggleWeight(key, checked)}
                      aria-label={`Учитывать: ${WEIGHT_LABELS[key] ?? key}`}
                    />
                  </div>
                </div>
                <Slider
                  type="single"
                  min={0}
                  max={100}
                  step={1}
                  value={customWeights[key] ?? 0}
                  onValueChange={(value) => onWeightChange(key, value)}
                  onValueCommit={() => void applyFilters()}
                  aria-label={WEIGHT_LABELS[key] ?? key}
                />
              </div>
            {/each}
          </div>
        </CardContent>
      </Card>
    </div>

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
        {#if result.is_stale}
          <CardHeader class="pb-3">
            <div class="flex justify-end">
              <Badge variant="outline">Кеш устарел — обновится в фоне</Badge>
            </div>
          </CardHeader>
        {/if}
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
                disabled={weightsVisible}
                onValueChange={(value) => {
                  if (value) changeSort(value as SortKey);
                }}
              >
                <Select.Trigger
                  class="w-48"
                  title={weightsVisible
                    ? "Пока панель «Формула рейтинга» открыта, сортировка — только по формуле"
                    : undefined}
                >
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
              <Button
                variant="outline"
                size="icon"
                onclick={() => (isListView = !isListView)}
                title={isListView ? "Показать обложками" : "Показать списком"}
                aria-label="Переключить вид"
              >
                {#if isListView}
                  <TextAlignJustify class="h-4 w-4" />
                {:else}
                  <LayoutGrid class="h-4 w-4" />
                {/if}
              </Button>
            </div>
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
            {#if isListView}
              <div class="rounded-lg border">
                <table class="w-full table-fixed caption-bottom text-sm">
                <Table.Header class="bg-card sticky top-14 z-10 border-b backdrop-blur">
                  <Table.Row>
                    <Table.Head class="w-16" title="Позиция в рейтинге bestfilmsof"># сайта</Table.Head>
                    <Table.Head class="w-16">Постер</Table.Head>
                    <Table.Head>Фильм</Table.Head>
                    <Table.Head class="w-20 text-right">Скор</Table.Head>
                    <Table.Head class="hidden w-24 text-right sm:table-cell">IMDb</Table.Head>
                    <Table.Head class="hidden w-24 text-right lg:table-cell">RT / Meta</Table.Head>
                    <Table.Head class="hidden w-28 text-right xl:table-cell">Награды</Table.Head>
                    <Table.Head class="hidden w-20 md:table-cell" />
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
                      <Table.Cell class="hidden text-right sm:table-cell">
                        {movie.imdb_rating == null ? "—" : movie.imdb_rating.toFixed(1)}
                        {#if movie.imdb_votes}
                          <div class="text-muted-foreground text-xs">{number(movie.imdb_votes)}</div>
                        {/if}
                      </Table.Cell>
                      <Table.Cell class="hidden text-right lg:table-cell">
                        {movie.tomato_meter == null ? "—" : movie.tomato_meter}
                        /
                        {movie.metascore == null ? "—" : movie.metascore}
                      </Table.Cell>
                      <Table.Cell class="hidden text-right text-xs xl:table-cell">
                        {movie.oscar_wins}W / {movie.oscar_nominations}N
                        {#if movie.best_picture}
                          <div class="text-amber-600 dark:text-amber-400">Best Picture</div>
                        {/if}
                      </Table.Cell>
                      <Table.Cell class="hidden md:table-cell">
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
              </div>
            {:else}
              <div class="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8">
                {#each visibleMovies as movie (movie.imdb_id)}
                  {@const poster = posterUrl(movie.poster_path, "w342")}
                  {@const href = movie.in_collection && movie.collection_slug ? `/movies/${movie.collection_slug}` : null}
                  <div class="group overflow-hidden rounded-lg border bg-card transition hover:shadow-md">
                    <a href={href ?? undefined} class="block">
                      <div class="relative aspect-[2/3] bg-muted">
                        {#if poster}
                          <VaultImage
                            src={poster}
                            alt={movieTitle(movie)}
                            class="h-full w-full object-cover"
                            slotClass="h-full w-full"
                            loading="lazy"
                          />
                        {:else}
                          <div class="text-muted-foreground flex h-full w-full items-center justify-center text-xs">
                            нет постера
                          </div>
                        {/if}
                        <Badge variant="secondary" class="absolute top-2 left-2 font-mono text-[10px]">
                          #{movie.position}
                        </Badge>
                        <MovieStatusBadges
                          watch_status={movie.watch_status}
                          rating={movie.rating}
                          is_favorite={movie.in_favorites}
                          year={movie.release_date ? Number(movie.release_date.slice(0, 4)) : null}
                        />
                        {#if movie.score != null}
                          <Badge class="absolute bottom-2 left-2 font-mono text-[10px]">
                            {movie.score.toFixed(2)}
                          </Badge>
                        {/if}
                      </div>
                      <div class="space-y-1 p-2">
                        <div class="line-clamp-2 text-sm font-medium" title={movieTitle(movie)}>
                          {movieTitle(movie)}
                        </div>
                        <div class="text-muted-foreground flex items-center gap-2 text-xs">
                          {#if movie.imdb_rating != null}
                            <span>IMDb {movie.imdb_rating.toFixed(1)}</span>
                          {/if}
                          {#if movie.imdb_votes}
                            <span>{number(movie.imdb_votes)}</span>
                          {/if}
                        </div>
                      </div>
                    </a>
                    {#if href}
                      <a
                        href={href}
                        class="text-muted-foreground hover:text-foreground flex items-center gap-1 px-2 pb-2 text-[10px]"
                      >
                        <ExternalLink class="h-3 w-3" />
                        В Vault
                      </a>
                    {/if}
                  </div>
                {/each}
              </div>
            {/if}
            <div bind:this={sentinelRef} class="flex h-12 items-center justify-center">
              {#if hasMore}
                <span class="text-muted-foreground flex items-center gap-2 text-xs">
                  <Loader2 class="h-4 w-4 animate-spin" />
                  Загружаем ещё…
                </span>
              {/if}
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
    {:else if year === "none" && genre === "all"}
      <Card>
        <CardContent class="text-muted-foreground py-10 text-sm">
          Год не выбран. Выберите год или жанр — для жанра без года покажем сводку по годам.
        </CardContent>
      </Card>
    {/if}
  {/if}
</div>
