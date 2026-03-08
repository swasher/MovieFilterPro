<script lang="ts">
  import { goto } from "$app/navigation";
  import { onDestroy, onMount, tick } from "svelte";
  import { Badge } from "$lib/components/ui/badge";
  import { Button } from "$lib/components/ui/button";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import KinozalPoster from "$lib/components/KinozalPoster.svelte";
  import * as Dialog from "$lib/components/ui/dialog";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import { Input } from "$lib/components/ui/input";
  import { Skeleton } from "$lib/components/ui/skeleton";
  import * as ToggleGroup from "$lib/components/ui/toggle-group";
  import {
    DEFAULT_PRIORITY_FILTER,
    DEFAULT_REVERSE,
    DEFAULT_SORT_KEY,
    type KinozalApiErrorDetail,
    type KinozalApiErrorPayload,
    KINOZAL_PRIORITY_OPTIONS,
    KINOZAL_PAGE_SIZE,
    KINOZAL_SORT_OPTIONS,
    type KinozalActionResponse,
    type KinozalDownloadOption,
    type KinozalDownloadOptionsResponse,
    emptyKinozalMoviesPage,
    emptyKinozalSummary,
    type KinozalMovie,
    type KinozalPriorityFilter,
    type KinozalSortKey,
    type KinozalSummary,
    type KinozalTorrentDownloadResponse,
    type KinozalMoviesPage
  } from "$lib/kinozal";
  import { toast } from "svelte-sonner";
  import {
    AlertCircle,
    ArrowDownToLine,
    ArrowDownUp,
    CircleDashed,
    Clapperboard,
    Clock3,
    EyeOff,
    ExternalLink,
    Film,
    Languages,
    RefreshCw,
    Search,
    X
  } from "@lucide/svelte";

  let { data } = $props();

  let movies = $state<KinozalMovie[]>([]);
  let summary = $state<KinozalSummary>(emptyKinozalSummary());
  let nextCursor = $state<string | null>(null);
  let hasMore = $state(false);
  let initialError = $state("");
  let summaryError = $state("");
  let loadMoreError = $state("");
  let isLoadingMore = $state(false);
  let sentinel = $state<HTMLDivElement | null>(null);
  let searchQuery = $state("");
  let activePriority = $state<KinozalPriorityFilter>(DEFAULT_PRIORITY_FILTER);
  let activeSort = $state<KinozalSortKey>(DEFAULT_SORT_KEY);
  let activeReverse = $state(DEFAULT_REVERSE);
  let filteredTotalCount = $state(0);
  let pendingActions = $state<Record<string, boolean>>({});
  let downloadDialogOpen = $state(false);
  let selectedMovie = $state<KinozalMovie | null>(null);
  let downloadOptions = $state<KinozalDownloadOption[]>([]);
  let downloadOptionsLoading = $state(false);
  let downloadOptionsError = $state<KinozalApiErrorDetail | null>(null);
  let downloadingTorrentId = $state<number | null>(null);
  let loadingDownloadMovieId = $state<number | null>(null);
  let stateVersion = 0;
  let debounceHandle: ReturnType<typeof setTimeout> | null = null;
  let snapshotKey = "";

  const KINOZAL_STATE_STORAGE_KEY = "kinozal-page-state";

  const priorityToneMap: Record<string, string> = {
    HIGH: "bg-emerald-500/12 text-emerald-700 dark:text-emerald-300 border border-emerald-500/20",
    LOW: "bg-sky-500/12 text-sky-700 dark:text-sky-300 border border-sky-500/20",
    DEFER: "bg-amber-500/12 text-amber-700 dark:text-amber-300 border border-amber-500/20",
    SKIP: "bg-rose-500/12 text-rose-700 dark:text-rose-300 border border-rose-500/20",
    WAIT_TRANS: "bg-violet-500/12 text-violet-700 dark:text-violet-300 border border-violet-500/20",
    TRANS_FOUND: "bg-cyan-500/12 text-cyan-700 dark:text-cyan-300 border border-cyan-500/20"
  };

  const formatRating = (value: number | null) => (value === null ? "—" : value.toFixed(1));
  const formatScanDate = (value: string) => {
    const [year = "", month = "", day = ""] = value.split("-");
    return year && month && day ? `${day}.${month}.${year}` : value;
  };

  const getSnapshotKey = () => `${window.location.pathname}${window.location.search}`;

  const savePageSnapshot = () => {
    if (!snapshotKey) {
      return;
    }

    const snapshot = {
      key: snapshotKey,
      movies,
      summary,
      nextCursor,
      hasMore,
      filteredTotalCount,
      initialError,
      summaryError,
      loadMoreError,
      activePriority,
      activeSort,
      activeReverse,
      searchQuery,
      scrollY: window.scrollY
    };

    sessionStorage.setItem(KINOZAL_STATE_STORAGE_KEY, JSON.stringify(snapshot));
  };

  const restorePageSnapshot = async () => {
    const rawSnapshot = sessionStorage.getItem(KINOZAL_STATE_STORAGE_KEY);
    if (!rawSnapshot) {
      return;
    }

    try {
      const snapshot = JSON.parse(rawSnapshot) as {
        key?: string;
        movies?: KinozalMovie[];
        summary?: KinozalSummary;
        nextCursor?: string | null;
        hasMore?: boolean;
        filteredTotalCount?: number;
        initialError?: string;
        summaryError?: string;
        loadMoreError?: string;
        activePriority?: KinozalPriorityFilter;
        activeSort?: KinozalSortKey;
        activeReverse?: boolean;
        searchQuery?: string;
        scrollY?: number;
      };

      if (snapshot.key !== snapshotKey) {
        return;
      }

      movies = snapshot.movies ?? movies;
      summary = snapshot.summary ?? summary;
      nextCursor = snapshot.nextCursor ?? nextCursor;
      hasMore = snapshot.hasMore ?? hasMore;
      filteredTotalCount = snapshot.filteredTotalCount ?? filteredTotalCount;
      initialError = snapshot.initialError ?? initialError;
      summaryError = snapshot.summaryError ?? summaryError;
      loadMoreError = snapshot.loadMoreError ?? "";
      activePriority = snapshot.activePriority ?? activePriority;
      activeSort = snapshot.activeSort ?? activeSort;
      activeReverse = snapshot.activeReverse ?? activeReverse;
      searchQuery = snapshot.searchQuery ?? searchQuery;

      await tick();
      window.scrollTo({ top: snapshot.scrollY ?? 0, behavior: "auto" });
    } catch {
      sessionStorage.removeItem(KINOZAL_STATE_STORAGE_KEY);
    }
  };

  const syncPageState = (page: KinozalMoviesPage, errorMessage: string) => {
    movies = [...page.items];
    summary = data.summary ?? emptyKinozalSummary();
    nextCursor = page.next_cursor;
    hasMore = page.has_more;
    filteredTotalCount = page.total_count ?? 0;
    initialError = errorMessage;
    summaryError = data.summaryError ?? "";
    activePriority = data.activePriority ?? DEFAULT_PRIORITY_FILTER;
    activeSort = data.activeSort ?? DEFAULT_SORT_KEY;
    activeReverse = data.activeReverse ?? DEFAULT_REVERSE;
    searchQuery = data.activeQuery ?? "";
    loadMoreError = "";
    isLoadingMore = false;
    stateVersion += 1;
  };

  $effect(() => {
    syncPageState(data.page ?? emptyKinozalMoviesPage(), data.apiError ?? "");
  });

  onMount(() => {
    snapshotKey = getSnapshotKey();
    void restorePageSnapshot();

    const handleBeforeUnload = () => {
      savePageSnapshot();
    };

    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  });

  onDestroy(() => {
    savePageSnapshot();
  });

  const navigateWithParams = async (next: {
    priority?: KinozalPriorityFilter;
    q?: string;
    sort?: KinozalSortKey;
    reverse?: boolean;
  }) => {
    const params = new URLSearchParams(window.location.search);
    const priority = next.priority ?? activePriority;
    const q = next.q ?? searchQuery;
    const sort = next.sort ?? activeSort;
    const reverse = next.reverse ?? activeReverse;

    if (priority && priority !== DEFAULT_PRIORITY_FILTER) {
      params.set("priority", priority);
    } else {
      params.delete("priority");
    }

    if (q.trim()) {
      params.set("q", q.trim());
    } else {
      params.delete("q");
    }

    if (sort && sort !== DEFAULT_SORT_KEY) {
      params.set("sort", sort);
    } else {
      params.delete("sort");
    }

    if (reverse !== DEFAULT_REVERSE) {
      params.set("reverse", "true");
    } else {
      params.delete("reverse");
    }

    const queryString = params.toString();
    await goto(queryString ? `/kinozal?${queryString}` : "/kinozal", {
      replaceState: true,
      keepFocus: true,
      noScroll: true,
      invalidateAll: true
    });
  };

  const fetchPage = async (
    cursor: string | null,
    filters: {
      priority: KinozalPriorityFilter;
      q: string;
      sort: KinozalSortKey;
      reverse: boolean;
    }
  ) => {
    const params = new URLSearchParams({ limit: String(KINOZAL_PAGE_SIZE) });
    if (cursor) {
      params.set("cursor", cursor);
    }
    if (filters.priority !== DEFAULT_PRIORITY_FILTER) {
      params.set("priority", filters.priority);
    }
    if (filters.q.trim()) {
      params.set("q", filters.q.trim());
    }
    if (filters.sort !== DEFAULT_SORT_KEY) {
      params.set("sort", filters.sort);
    }
    if (filters.reverse !== DEFAULT_REVERSE) {
      params.set("reverse", "true");
    }

    const response = await fetch(`/api/kinozal/movies?${params.toString()}`);
    let payload: KinozalMoviesPage | { detail?: string } | null = null;

    try {
      payload = (await response.json()) as KinozalMoviesPage | { detail?: string };
    } catch {
      payload = null;
    }

    if (!response.ok) {
      const detail =
        payload && "detail" in payload && typeof payload.detail === "string" && payload.detail.trim()
          ? payload.detail.trim()
          : `API error: ${response.status}`;
      throw new Error(detail);
    }

    return payload as KinozalMoviesPage;
  };

  const loadMore = async () => {
    if (!hasMore || !nextCursor || isLoadingMore || initialError) {
      return;
    }

    const requestVersion = stateVersion;
    const filters = {
      priority: activePriority,
      q: searchQuery,
      sort: activeSort,
      reverse: activeReverse
    };
    isLoadingMore = true;
    loadMoreError = "";

    try {
      const page = await fetchPage(nextCursor, filters);
      if (requestVersion !== stateVersion) {
        return;
      }
      movies = [...movies, ...page.items];
      nextCursor = page.next_cursor;
      hasMore = page.has_more;
    } catch (error) {
      loadMoreError = error instanceof Error ? error.message : "Unknown API error";
    } finally {
      isLoadingMore = false;
    }
  };

  const retryLoadMore = async () => {
    loadMoreError = "";
    await loadMore();
  };

  const priorityLabelMap: Record<string, string> = {
    HIGH: "Обычный",
    LOW: "Низкий",
    DEFER: "Отложено",
    SKIP: "Отказ",
    WAIT_TRANS: "Жду дубляж",
    TRANS_FOUND: "Найден дубляж или ПМ"
  };

  const actionKey = (movieId: number, action: string) => `${movieId}:${action}`;
  const isActionPending = (movieId: number, action: string) => Boolean(pendingActions[actionKey(movieId, action)]);
  const setActionPending = (movieId: number, action: string, isPending: boolean) => {
    const key = actionKey(movieId, action);
    pendingActions = {
      ...pendingActions,
      [key]: isPending
    };
  };

  const patchMoviePriority = (movieId: number, priorityKey: string) => {
    movies = movies.map((movie) =>
      movie.id === movieId
        ? {
            ...movie,
            priority_key: priorityKey,
            priority_label: priorityLabelMap[priorityKey] ?? priorityKey
          }
        : movie
    );
  };

  const adjustSummaryCount = (priorityKey: string, delta: number) => {
    if (priorityKey === "HIGH") summary.high += delta;
    if (priorityKey === "LOW") summary.low += delta;
    if (priorityKey === "DEFER") summary.defer += delta;
    if (priorityKey === "SKIP") summary.skip += delta;
    if (priorityKey === "WAIT_TRANS") summary.wait_trans += delta;
    if (priorityKey === "TRANS_FOUND") summary.trans_found += delta;
    summary.total = summary.high + summary.low + summary.defer;
  };

  const applyPriorityTransition = (previousPriorityKey: string, currentPriorityKey: string) => {
    summary = { ...summary };
    adjustSummaryCount(previousPriorityKey, -1);
    adjustSummaryCount(currentPriorityKey, 1);
  };

  const maybeTopUpAfterRemoval = () => {
    if (hasMore && movies.length < KINOZAL_PAGE_SIZE && !isLoadingMore) {
      void loadMore();
    }
  };

  const performMovieAction = async (
    movie: KinozalMovie,
    action: "hide" | "defer" | "wait-trans",
    targetPriorityKey: string
  ) => {
    const previousMovies = [...movies];
    const previousSummary = { ...summary };
    const previousFilteredTotalCount = filteredTotalCount;
    const shouldRemoveFromCurrentView =
      activePriority !== DEFAULT_PRIORITY_FILTER && activePriority !== targetPriorityKey;

    setActionPending(movie.id, action, true);

    if (shouldRemoveFromCurrentView) {
      movies = movies.filter((item) => item.id !== movie.id);
      filteredTotalCount = Math.max(0, filteredTotalCount - 1);
    } else {
      patchMoviePriority(movie.id, targetPriorityKey);
    }
    applyPriorityTransition(movie.priority_key, targetPriorityKey);

    try {
      const response = await fetch(`/api/kinozal/movies/${movie.id}/${action}`, {
        method: "POST"
      });
      const payload = (await response.json()) as KinozalActionResponse | { detail?: string };

      if (!response.ok) {
        throw new Error(
          "detail" in payload && typeof payload.detail === "string" ? payload.detail : `HTTP ${response.status}`
        );
      }

      const successPayload = payload as KinozalActionResponse;
      toast.success(successPayload.message);
      if (shouldRemoveFromCurrentView) {
        maybeTopUpAfterRemoval();
      }
    } catch (error) {
      movies = previousMovies;
      summary = previousSummary;
      filteredTotalCount = previousFilteredTotalCount;
      toast.error(error instanceof Error ? error.message : "Action failed");
    } finally {
      setActionPending(movie.id, action, false);
    }
  };

  const openDownloadDialog = async (movie: KinozalMovie) => {
    selectedMovie = movie;
    downloadDialogOpen = true;
    downloadOptions = [];
    downloadOptionsError = null;
    downloadOptionsLoading = true;
    loadingDownloadMovieId = movie.id;

    try {
      const response = await fetch(`/api/kinozal/movies/${movie.id}/download-options`);
      const payload = (await response.json()) as KinozalDownloadOptionsResponse | KinozalApiErrorPayload;

      if (!response.ok) {
        throw parseKinozalApiError(payload, `HTTP ${response.status}`);
      }

      const successPayload = payload as KinozalDownloadOptionsResponse;
      downloadOptions = successPayload.items;
    } catch (error) {
      downloadOptionsError = normalizeClientError(error, "Не удалось загрузить варианты скачивания.");
      toast.error(downloadOptionsError.message ?? "Не удалось загрузить варианты скачивания.");
    } finally {
      loadingDownloadMovieId = null;
      downloadOptionsLoading = false;
    }
  };

  const downloadTorrent = async (torrentId: number) => {
    downloadingTorrentId = torrentId;

    try {
      const response = await fetch(`/api/kinozal/torrents/${torrentId}/download`, {
        method: "POST"
      });
      const payload = (await response.json()) as KinozalTorrentDownloadResponse | KinozalApiErrorPayload;

      if (!response.ok) {
        throw parseKinozalApiError(payload, `HTTP ${response.status}`);
      }

      const successPayload = payload as KinozalTorrentDownloadResponse;
      toast.success(successPayload.message);
    } catch (error) {
      const normalizedError = normalizeClientError(error, "Скачать torrent-файл не удалось.");
      downloadOptionsError = normalizedError;
      toast.error(normalizedError.message ?? "Скачать torrent-файл не удалось.");
    } finally {
      downloadingTorrentId = null;
    }
  };

  const parseKinozalApiError = (
    payload: KinozalApiErrorPayload | KinozalDownloadOptionsResponse | KinozalTorrentDownloadResponse,
    fallbackMessage: string
  ): KinozalApiErrorDetail => {
    const detail = "detail" in payload ? payload.detail : undefined;
    if (!detail) {
      return { message: fallbackMessage };
    }
    if (typeof detail === "string") {
      try {
        const parsed = JSON.parse(detail) as KinozalApiErrorDetail;
        if (parsed && typeof parsed === "object") {
          return {
            code: parsed.code,
            message: parsed.message || fallbackMessage,
            hint: parsed.hint
          };
        }
      } catch {
        // fall back to plain string message
      }
      return { message: detail };
    }
    return {
      code: detail.code,
      message: detail.message || fallbackMessage,
      hint: detail.hint
    };
  };

  const normalizeClientError = (error: unknown, fallbackMessage: string): KinozalApiErrorDetail => {
    if (error && typeof error === "object" && ("message" in error || "code" in error || "hint" in error)) {
      const detail = error as KinozalApiErrorDetail;
      return {
        code: detail.code,
        message: detail.message || fallbackMessage,
        hint: detail.hint
      };
    }

    if (error instanceof Error) {
      return { message: error.message || fallbackMessage };
    }

    return { message: fallbackMessage };
  };

  const canFixDownloadErrorInPreferences = (error: KinozalApiErrorDetail | null) =>
    Boolean(
      error?.code &&
        ["settings_missing_domain", "settings_missing_auth", "settings_missing_hotfolder"].includes(error.code)
    );

  const retryDownloadOptions = async () => {
    if (!selectedMovie) {
      return;
    }
    await openDownloadDialog(selectedMovie);
  };

  const onPriorityChange = async (value: string) => {
    await navigateWithParams({
      priority: (value || DEFAULT_PRIORITY_FILTER) as KinozalPriorityFilter
    });
  };

  const onSortChange = async (value: string) => {
    await navigateWithParams({
      sort: value as KinozalSortKey
    });
  };

  const onReverseToggle = async () => {
    await navigateWithParams({
      reverse: !activeReverse
    });
  };

  const applySearch = async () => {
    await navigateWithParams({
      q: searchQuery
    });
  };

  const onSearchInput = () => {
    if (debounceHandle) {
      clearTimeout(debounceHandle);
    }

    debounceHandle = setTimeout(() => {
      void applySearch();
    }, 300);
  };

  const clearSearch = async () => {
    searchQuery = "";
    if (debounceHandle) {
      clearTimeout(debounceHandle);
      debounceHandle = null;
    }
    await navigateWithParams({ q: "" });
  };

  $effect(() => {
    const node = sentinel;

    if (!node || !hasMore || !nextCursor || isLoadingMore || initialError || loadMoreError) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            void loadMore();
            break;
          }
        }
      },
      {
        rootMargin: "600px 0px"
      }
    );

    observer.observe(node);

    return () => {
      observer.disconnect();
    };
  });

  const totalLoaded = $derived(movies.length);
  const filteredTotal = $derived(filteredTotalCount);
  const summaryCards = $derived([
    { label: "Last scan", value: summary.last_scan ? formatScanDate(summary.last_scan) : "—", tone: "success" },
    { label: "Total", value: String(summary.total), tone: "success" },
    { label: "High", value: String(summary.high), tone: "default" },
    { label: "Low", value: String(summary.low), tone: "default" },
    { label: "Defer", value: String(summary.defer), tone: "default" },
    { label: "Skip", value: String(summary.skip), tone: "muted" },
    { label: "Wait trans", value: String(summary.wait_trans), tone: "muted" },
    { label: "Trans found", value: String(summary.trans_found), tone: "success" }
  ]);

  const badgeToneClass = (tone: string) => {
    if (tone === "success") {
      return "border-emerald-500/25 bg-emerald-500/12 text-emerald-700 dark:text-emerald-300";
    }
    if (tone === "muted") {
      return "border-border bg-muted text-muted-foreground";
    }
    return "border-slate-500/20 bg-slate-500/10 text-slate-700 dark:text-slate-300";
  };

  const compactList = (items: string[], limit: number) => items.filter(Boolean).slice(0, limit);
  const activeSortLabel = $derived(
    KINOZAL_SORT_OPTIONS.find((item) => item.value === activeSort)?.label ?? "Сортировка"
  );
  const hasActiveFilters = $derived(
    activePriority !== DEFAULT_PRIORITY_FILTER || searchQuery.trim() !== "" || activeSort !== DEFAULT_SORT_KEY || activeReverse !== DEFAULT_REVERSE
  );
</script>

<div class="mx-auto flex w-full max-w-[1500px] flex-col gap-6 p-4 md:p-6">
  <Card class="border-border/70 bg-gradient-to-br from-background via-background to-muted/30">
    <CardHeader class="gap-4 md:flex-row md:items-center md:justify-between">
      <div class="space-y-2">
        <div class="flex flex-wrap items-center gap-2">
          <CardTitle class="text-2xl">Kinozal</CardTitle>
          <Badge variant="secondary">Phase 5</Badge>
          <Badge variant="outline">Download flow</Badge>
        </div>
        <CardDescription class="max-w-3xl text-sm leading-relaxed">
          Экран `MovieRSS` на новом API с query state, row actions и download flow с обработкой ошибок и inline retry.
        </CardDescription>
      </div>

        <div class="flex flex-wrap items-center gap-2 text-sm">
          <Badge variant="outline" class="px-3 py-1">
            <Film class="mr-1 size-3.5" />
            Загружено: {totalLoaded}
          </Badge>
          <Badge variant="outline" class="px-3 py-1">
            Найдено: {filteredTotal}
          </Badge>
          <a
            href="http://127.0.0.1:8000/"
            target="_blank"
          rel="noreferrer"
          class="text-sm font-medium underline underline-offset-4"
        >
          Открыть текущий Django UI
        </a>
      </div>
    </CardHeader>
  </Card>

  {#if !initialError}
    <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {#each summaryCards as item (item.label)}
        <Card class="border-border/70">
          <CardContent class="flex items-center justify-between gap-3 py-4">
            <div class="space-y-1">
              <p class="text-muted-foreground text-[11px] uppercase tracking-[0.18em]">{item.label}</p>
              <p class="text-lg font-semibold">{item.value}</p>
            </div>
            <span class={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${badgeToneClass(item.tone)}`}>
              {item.label}
            </span>
          </CardContent>
        </Card>
      {/each}
    </div>
  {/if}

  {#if summaryError && !initialError}
    <Card class="border-amber-500/30">
      <CardContent class="flex items-center gap-3 py-4 text-sm text-muted-foreground">
        <Clapperboard class="size-4 text-amber-600 dark:text-amber-300" />
        <span>Summary-метрики загрузить не удалось: {summaryError}</span>
      </CardContent>
    </Card>
  {/if}

  {#if !initialError}
    <Card class="border-border/70">
      <CardContent class="flex flex-col gap-4 py-4">
        <div class="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div class="flex flex-1 items-center gap-2">
            <div class="relative flex-1">
              <Search class="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2" />
              <Input
                bind:value={searchQuery}
                type="search"
                placeholder="Поиск по title / original title / year..."
                class="h-11 pl-9 pr-10"
                oninput={onSearchInput}
              />
              {#if searchQuery.trim()}
                <button
                  type="button"
                  class="text-muted-foreground hover:text-foreground absolute right-3 top-1/2 -translate-y-1/2"
                  onclick={clearSearch}
                  aria-label="Clear search"
                >
                  <X class="size-4" />
                </button>
              {/if}
            </div>

            <DropdownMenu.Root>
              <DropdownMenu.Trigger>
                {#snippet child({ props })}
                  <Button {...props} variant="outline" class="h-11 min-w-[190px] justify-between">
                    {activeSortLabel}
                    <ArrowDownUp class="size-4" />
                  </Button>
                {/snippet}
              </DropdownMenu.Trigger>
              <DropdownMenu.Content class="w-56" align="end">
                <DropdownMenu.RadioGroup value={activeSort} onValueChange={onSortChange}>
                  {#each KINOZAL_SORT_OPTIONS as option (option.value)}
                    <DropdownMenu.RadioItem value={option.value}>
                      {option.label}
                    </DropdownMenu.RadioItem>
                  {/each}
                </DropdownMenu.RadioGroup>
              </DropdownMenu.Content>
            </DropdownMenu.Root>

            <Button variant="outline" class="h-11 min-w-[120px]" onclick={onReverseToggle}>
              <ArrowDownUp class="mr-2 size-4" />
              {activeReverse ? "Reverse on" : "Reverse off"}
            </Button>
          </div>
        </div>

        <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div class="overflow-x-auto">
            <ToggleGroup.Root
              type="single"
              value={activePriority}
              variant="outline"
              class="w-max min-w-full"
              onValueChange={onPriorityChange}
            >
              {#each KINOZAL_PRIORITY_OPTIONS as option (option.value)}
                <ToggleGroup.Item value={option.value}>
                  {option.label}
                </ToggleGroup.Item>
              {/each}
            </ToggleGroup.Root>
          </div>

          <div class="flex flex-wrap items-center gap-2 text-sm">
            {#if activePriority !== DEFAULT_PRIORITY_FILTER}
              <Badge variant="secondary">Priority: {activePriority}</Badge>
            {/if}
            {#if data.activeQuery}
              <Badge variant="secondary">Query: {data.activeQuery}</Badge>
            {/if}
            {#if activeSort !== DEFAULT_SORT_KEY}
              <Badge variant="secondary">Sort: {activeSortLabel}</Badge>
            {/if}
            {#if activeReverse}
              <Badge variant="secondary">Reverse</Badge>
            {/if}
            {#if hasActiveFilters}
              <Button
                variant="ghost"
                class="h-8 px-2 text-muted-foreground"
                onclick={() => navigateWithParams({
                  priority: DEFAULT_PRIORITY_FILTER,
                  q: "",
                  sort: DEFAULT_SORT_KEY,
                  reverse: DEFAULT_REVERSE
                })}
              >
                Сбросить
              </Button>
            {/if}
          </div>
        </div>
      </CardContent>
    </Card>
  {/if}

  {#if initialError}
    <Card class="border-destructive/40">
      <CardHeader>
        <div class="flex items-center gap-2">
          <AlertCircle class="text-destructive size-5" />
          <CardTitle>Не удалось загрузить список</CardTitle>
        </div>
        <CardDescription>{initialError}</CardDescription>
      </CardHeader>
    </Card>
  {:else if movies.length === 0}
    <Card>
      <CardHeader>
        <CardTitle>Список пуст</CardTitle>
        <CardDescription>
          {#if hasActiveFilters}
            По текущим фильтрам и поиску ничего не найдено.
          {:else}
            MovieRSS сейчас не содержит фильмов для отображения.
          {/if}
        </CardDescription>
      </CardHeader>
    </Card>
  {:else}
    <Card class="overflow-hidden border-border/70">
      <CardContent class="p-0">
        <div class="overflow-x-auto">
          <table class="w-full min-w-[1380px] table-fixed border-collapse">
            <thead class="bg-muted/50">
              <tr class="text-left">
                <th class="w-[120px] px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Poster</th>
                <th class="w-[320px] px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Title</th>
                <th class="w-[170px] px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Some data</th>
                <th class="w-[320px] px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Common</th>
                <th class="px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Plot</th>
                <th class="w-[220px] px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Translate</th>
                <th class="w-[170px] px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {#each movies as movie (movie.id)}
                <tr class={`border-t align-top ${movie.kinorium_partial_match ? "bg-amber-500/6" : "bg-background"}`}>
                  <td class="px-4 py-4">
                    <KinozalPoster src={movie.poster_url} alt={`Poster of ${movie.title}`} />
                  </td>
                  <td class="px-4 py-4">
                    <div class="space-y-3">
                      <div class="space-y-1.5">
                        <p class="text-base font-semibold leading-tight">{movie.title}</p>
                        <p class="text-muted-foreground text-sm leading-snug">
                          {movie.original_title || "—"}
                        </p>
                      </div>

                      <div class="flex flex-wrap gap-2">
                        <span class={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-medium ${priorityToneMap[movie.priority_key] ?? "bg-muted text-muted-foreground border border-border"}`}>
                          {movie.priority_label}
                        </span>
                        {#if movie.kinorium_partial_match}
                          <span class="inline-flex rounded-full border border-amber-500/20 bg-amber-500/12 px-2.5 py-1 text-[11px] font-medium text-amber-700 dark:text-amber-300">
                            Partial match
                          </span>
                        {/if}
                      </div>

                      <div class="text-muted-foreground flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.16em]">
                        <span>ID {movie.kinozal_id}</span>
                      </div>
                    </div>
                  </td>
                  <td class="px-4 py-4">
                    <div class="space-y-2 text-sm">
                      <div class="rounded-lg border border-border/70 px-3 py-2">
                        <p class="text-muted-foreground text-[11px] uppercase tracking-[0.16em]">Year</p>
                        <p class="font-semibold">{movie.year}</p>
                      </div>
                      <div class="rounded-lg border border-border/70 px-3 py-2">
                        <p class="text-muted-foreground text-[11px] uppercase tracking-[0.16em]">IMDB</p>
                        <p class="text-sm font-semibold">{formatRating(movie.imdb_rating)}</p>
                      </div>
                      <div class="rounded-lg border border-border/70 px-3 py-2">
                        <p class="text-muted-foreground text-[11px] uppercase tracking-[0.16em]">KP</p>
                        <p class="text-sm font-semibold">{formatRating(movie.kinopoisk_rating)}</p>
                      </div>
                      <div class="rounded-lg border border-border/70 px-3 py-2">
                        <p class="text-muted-foreground text-[11px] uppercase tracking-[0.16em]">Scan</p>
                        <p class="text-sm font-semibold">{formatScanDate(movie.date_added)}</p>
                      </div>
                    </div>
                  </td>
                  <td class="px-4 py-4">
                    <div class="space-y-3 text-sm">
                      <div class="space-y-1.5">
                        <p class="text-muted-foreground text-[11px] uppercase tracking-[0.16em]">Genres</p>
                        <div class="flex flex-wrap gap-1.5">
                          {#each compactList(movie.genres, 8) as genre (genre)}
                            <span class="rounded-full border border-border/70 bg-muted/60 px-2 py-1 text-[11px] leading-none">
                              {genre}
                            </span>
                          {/each}
                        </div>
                      </div>

                      <div class="space-y-1.5">
                        <p class="text-muted-foreground text-[11px] uppercase tracking-[0.16em]">Countries</p>
                        <div class="flex flex-wrap gap-1.5">
                          {#each compactList(movie.countries, 6) as country (country)}
                            <span class="rounded-full border border-border/70 bg-muted/60 px-2 py-1 text-[11px] leading-none">
                              {country}
                            </span>
                          {/each}
                        </div>
                      </div>

                      <div class="space-y-1.5">
                        <p class="text-muted-foreground text-[11px] uppercase tracking-[0.16em]">Director</p>
                        <div class="flex flex-wrap gap-1.5">
                          {#each compactList(movie.directors, 4) as director (director)}
                            <span class="rounded-full border border-border/70 bg-muted/60 px-2 py-1 text-[11px] leading-none">
                              {director}
                            </span>
                          {/each}
                        </div>
                      </div>

                      <div class="space-y-1.5">
                        <p class="text-muted-foreground text-[11px] uppercase tracking-[0.16em]">Actors</p>
                        <div class="flex flex-wrap gap-1.5">
                          {#each compactList(movie.actors, 6) as actor (actor)}
                            <span class="rounded-full border border-border/70 bg-muted/60 px-2 py-1 text-[11px] leading-none">
                              {actor}
                            </span>
                          {/each}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td class="px-4 py-4">
                    <p class="text-sm leading-6 text-foreground/90 [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:8] overflow-hidden">
                      {movie.plot || "—"}
                    </p>
                  </td>
                  <td class="px-4 py-4">
                    <p class="text-sm leading-6 text-foreground/90">
                      {movie.translate || "—"}
                    </p>
                  </td>
                  <td class="px-4 py-4">
                    <div class="flex flex-col gap-2">
                      <Button
                        href={movie.open_url ?? undefined}
                        target="_blank"
                        rel="noreferrer"
                        variant="outline"
                        size="sm"
                        disabled={!movie.open_url}
                      >
                        <ExternalLink class="mr-2 size-4" />
                        Open
                      </Button>

                      <Button
                        variant="secondary"
                        size="sm"
                        onclick={() => openDownloadDialog(movie)}
                        disabled={loadingDownloadMovieId === movie.id}
                      >
                        <ArrowDownToLine class="mr-2 size-4" />
                        {loadingDownloadMovieId === movie.id ? "..." : "Download"}
                      </Button>

                      <Button
                        variant="outline"
                        size="sm"
                        onclick={() => performMovieAction(movie, "defer", "DEFER")}
                        disabled={isActionPending(movie.id, "defer")}
                      >
                        <Clock3 class="mr-2 size-4" />
                        {isActionPending(movie.id, "defer") ? "..." : "Defer"}
                      </Button>

                      <Button
                        variant="outline"
                        size="sm"
                        onclick={() => performMovieAction(movie, "wait-trans", "WAIT_TRANS")}
                        disabled={isActionPending(movie.id, "wait-trans")}
                      >
                        <Languages class="mr-2 size-4" />
                        {isActionPending(movie.id, "wait-trans") ? "..." : "Wait trans"}
                      </Button>

                      <Button
                        variant="destructive"
                        size="sm"
                        onclick={() => performMovieAction(movie, "hide", "SKIP")}
                        disabled={isActionPending(movie.id, "hide")}
                      >
                        <EyeOff class="mr-2 size-4" />
                        {isActionPending(movie.id, "hide") ? "..." : "Hide"}
                      </Button>
                    </div>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>

    {#if loadMoreError}
      <Card class="border-destructive/30">
        <CardHeader>
          <CardTitle class="text-base">Ошибка догрузки</CardTitle>
          <CardDescription>{loadMoreError}</CardDescription>
        </CardHeader>
        <CardContent class="pt-0">
          <Button variant="outline" class="gap-2" onclick={retryLoadMore}>
            <RefreshCw class="size-4" />
            Повторить
          </Button>
        </CardContent>
      </Card>
    {/if}

    {#if isLoadingMore}
      <Card>
        <CardContent class="flex items-center gap-4 py-5">
          <CircleDashed class="text-muted-foreground size-5 animate-spin" />
          <div class="grid flex-1 gap-2">
            <Skeleton class="h-4 w-32" />
            <Skeleton class="h-4 w-full" />
          </div>
        </CardContent>
      </Card>
    {/if}

    {#if !hasMore}
      <Card>
        <CardContent class="py-5 text-sm text-muted-foreground">
          Все доступные записи загружены.
        </CardContent>
      </Card>
    {/if}

    <div bind:this={sentinel} class="h-10 w-full" aria-hidden="true"></div>
  {/if}
</div>

<Dialog.Root bind:open={downloadDialogOpen}>
  <Dialog.Content class="max-w-5xl">
    <Dialog.Header>
      <Dialog.Title>Available torrents</Dialog.Title>
      <Dialog.Description>
        {#if selectedMovie}
          {selectedMovie.title}
        {:else}
          Kinozal options
        {/if}
      </Dialog.Description>
    </Dialog.Header>

    {#if downloadOptionsLoading}
      <div class="grid gap-3">
        <Skeleton class="h-10 w-full" />
        <Skeleton class="h-10 w-full" />
        <Skeleton class="h-10 w-full" />
      </div>
    {:else if downloadOptionsError}
      <div class="space-y-3 rounded-lg border border-destructive/30 px-4 py-4">
        <div class="space-y-1">
          <p class="text-sm font-semibold text-destructive">
            {downloadOptionsError.message || "Download flow error"}
          </p>
          {#if downloadOptionsError.hint}
            <p class="text-sm text-muted-foreground">
              {downloadOptionsError.hint}
            </p>
          {/if}
        </div>
        <div class="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onclick={retryDownloadOptions} disabled={downloadOptionsLoading}>
            <RefreshCw class="mr-2 size-4" />
            Retry
          </Button>
          {#if canFixDownloadErrorInPreferences(downloadOptionsError)}
            <Button variant="secondary" size="sm" href="/preferences">
              Open Preferences
            </Button>
          {/if}
        </div>
      </div>
    {:else if downloadOptions.length === 0}
      <div class="rounded-lg border px-4 py-3 text-sm text-muted-foreground">
        Подходящих вариантов не найдено.
      </div>
    {:else}
      <div class="max-h-[70vh] overflow-auto">
        <table class="w-full min-w-[900px] table-fixed border-collapse">
          <thead class="bg-muted/50">
            <tr class="text-left">
              <th class="px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Title</th>
              <th class="w-[100px] px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Size</th>
              <th class="w-[80px] px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Seed</th>
              <th class="w-[80px] px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Peer</th>
              <th class="w-[120px] px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Created</th>
              <th class="w-[170px] px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Actions</th>
            </tr>
          </thead>
          <tbody>
            {#each downloadOptions as option (option.id)}
              <tr class="border-t align-top">
                <td class="px-3 py-3">
                  <div class="space-y-1">
                    <div class="flex flex-wrap gap-2">
                      {#if option.is_4k}
                        <Badge variant="secondary">4K</Badge>
                      {/if}
                      {#if option.is_sdr}
                        <Badge variant="outline">SDR</Badge>
                      {/if}
                    </div>
                    <a href={option.link} target="_blank" rel="noreferrer" class="text-sm font-medium underline underline-offset-4">
                      {option.header}
                    </a>
                  </div>
                </td>
                <td class="px-3 py-3 text-sm">{option.size}</td>
                <td class="px-3 py-3 text-sm">{option.seed}</td>
                <td class="px-3 py-3 text-sm">{option.peer}</td>
                <td class="px-3 py-3 text-sm">{option.created}</td>
                <td class="px-3 py-3">
                  <div class="flex gap-2">
                    <Button variant="outline" size="sm" href={option.link} target="_blank" rel="noreferrer">
                      <ExternalLink class="mr-2 size-4" />
                      Open
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onclick={() => downloadTorrent(option.id)}
                      disabled={downloadingTorrentId === option.id}
                    >
                      <ArrowDownToLine class="mr-2 size-4" />
                      {downloadingTorrentId === option.id ? "..." : "Down"}
                    </Button>
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </Dialog.Content>
</Dialog.Root>
