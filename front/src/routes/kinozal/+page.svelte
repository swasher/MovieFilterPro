<script lang="ts">
  import { goto } from "$app/navigation";
  import { onDestroy, onMount, tick } from "svelte";
  import "./kinozal.css";
  import { Button } from "$lib/components/ui/button";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import BootstrapBadge4kFill from "$lib/components/BootstrapBadge4kFill.svelte";
  import BootstrapBadgeSdFill from "$lib/components/BootstrapBadgeSdFill.svelte";
  import KinozalPoster from "$lib/components/KinozalPoster.svelte";
  import * as Dialog from "$lib/components/ui/dialog";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import { Input } from "$lib/components/ui/input";
  import { Skeleton } from "$lib/components/ui/skeleton";
  import { Toggle } from "$lib/components/ui/toggle";
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
  let leavingRows = $state<Record<number, boolean>>({});
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

  const KINOZAL_STATE_STORAGE_KEY = "kinozal-page-state-v2";

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
  const formatCreatedDate = (value: string) => value.split(" ")[0] || value;
  const compactList = (items: string[], limit: number) => items.filter(Boolean).slice(0, limit);
  const compactTextList = (items: string[], limit: number) => {
    const result = compactList(items, limit).join(", ");
    return result || "—";
  };

  const getKinoriumUrl = (movie: KinozalMovie) => {
    if (movie.kinorium_url) {
      return movie.kinorium_url;
    }
    const parts = [movie.title, movie.original_title, movie.year].filter(Boolean);
    const query = parts.join(" ");
    return `https://ru.kinorium.com/search/?q=${encodeURIComponent(query)}`;
  };

  const getTmdbUrl = (movie: KinozalMovie) => {
    const query = movie.original_title?.trim() || movie.title;
    return `https://www.themoviedb.org/search?query=${encodeURIComponent(query)}`;
  };

  const getImdbUrl = (movie: KinozalMovie) => {
    const rawId = movie.imdb_id?.toString().trim();
    if (rawId) {
      const formattedId = rawId.startsWith("tt") ? rawId : `tt${rawId}`;
      return `https://www.imdb.com/title/${formattedId}/`;
    }
    const query = movie.original_title?.trim() || movie.title;
    return `https://www.imdb.com/find/?q=${encodeURIComponent(query)}`;
  };

  const getKinopoiskUrl = (movie: KinozalMovie) => {
    const rawId = movie.kinopoisk_id?.toString().trim();
    if (rawId) {
      return `https://www.kinopoisk.ru/film/${rawId}/`;
    }
    const query = movie.title;
    return `https://www.kinopoisk.ru/index.php?kp_query=${encodeURIComponent(query)}`;
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

      const hasFatalSnapshotError = Boolean((snapshot.initialError ?? "").trim());
      if (hasFatalSnapshotError) {
        sessionStorage.removeItem(KINOZAL_STATE_STORAGE_KEY);
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

    if (priority === "ALL") {
      params.set("priority", priority);
    } else if (priority && priority !== DEFAULT_PRIORITY_FILTER) {
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
    if (filters.priority !== "ALL") {
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
  const isRowLeaving = (movieId: number) => Boolean(leavingRows[movieId]);
  const setActionPending = (movieId: number, action: string, isPending: boolean) => {
    const key = actionKey(movieId, action);
    pendingActions = {
      ...pendingActions,
      [key]: isPending
    };
  };
  const setRowLeaving = (movieId: number, isLeaving: boolean) => {
    leavingRows = {
      ...leavingRows,
      [movieId]: isLeaving
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
    const shouldRemoveFromCurrentView = activePriority !== "ALL" && activePriority !== targetPriorityKey;

    setActionPending(movie.id, action, true);

    if (shouldRemoveFromCurrentView) {
      setRowLeaving(movie.id, true);
      await new Promise((resolve) => setTimeout(resolve, 180));
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
      setRowLeaving(movie.id, false);
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
        method: "POST",
        headers: {
          "content-type": "application/json"
        },
        body: JSON.stringify({
          movie_id: selectedMovie?.id ?? null
        })
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
  const activeSortLabel = $derived(
    KINOZAL_SORT_OPTIONS.find((item) => item.value === activeSort)?.label ?? "Сортировка"
  );
  const activePriorityLabel = $derived(
    KINOZAL_PRIORITY_OPTIONS.find((item) => item.value === activePriority)?.label ?? activePriority
  );
  const summaryCards = $derived([
    { label: "Последний скан", value: summary.last_scan ? formatScanDate(summary.last_scan) : "—", tone: "success" },
    { label: "High", value: String(summary.high), tone: "primary" },
    { label: "Defer / Low", value: `${summary.defer} / ${summary.low}`, tone: "muted" },
    { label: "Skip", value: String(summary.skip), tone: "danger-muted" },
    { label: "Жду дубляж / найдено", value: `${summary.wait_trans} / ${summary.trans_found}`, tone: "muted" }
  ]);

  const summaryToneClass = (tone: string) => {
    if (tone === "success") {
      return "kz-summary-item--success";
    }
    if (tone === "muted") {
      return "kz-summary-item--muted";
    }
    if (tone === "primary") {
      return "kz-summary-item--primary";
    }
    if (tone === "danger-muted") {
      return "kz-summary-item--danger-muted";
    }
    return "";
  };

  const hasActiveFilters = $derived(
    activePriority !== DEFAULT_PRIORITY_FILTER || searchQuery.trim() !== "" || activeSort !== DEFAULT_SORT_KEY || activeReverse !== DEFAULT_REVERSE
  );
</script>

<div class="kz-page">
  {#if !initialError}
    <div class="kz-summary-strip">
      {#each summaryCards as item (item.label)}
        <div class={`kz-summary-item ${summaryToneClass(item.tone)}`}>
          <span class="kz-summary-label">{item.label}:</span>
          <span class="kz-summary-value">{item.value}</span>
        </div>
      {/each}
    </div>
  {/if}

  {#if summaryError && !initialError}
    <div class="kz-inline-alert kz-inline-alert--warning">
      <Clapperboard class="size-4 shrink-0 text-amber-600 dark:text-amber-300" />
      <span>Summary-метрики загрузить не удалось: {summaryError}</span>
    </div>
  {/if}

  {#if !initialError}
    <div class="kz-toolbar">
      <div class="kz-toolbar-main">
        <div class="kz-toolbar-left">
          <div class="kz-toggle-wrap">
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
        </div>

        <div class="kz-toolbar-right">
          <div class="kz-toolbar-search">
            <Search class="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2" />
            <Input
              bind:value={searchQuery}
              type="search"
              placeholder="Поиск по title / original title / year..."
              class="h-10 min-w-[260px] pl-10 pr-10"
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
                <Button {...props} variant="outline" class="kz-toolbar-button">
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

          <Toggle
            pressed={activeReverse}
            variant="outline"
            size="default"
            class="kz-toolbar-icon-button"
            aria-label="Toggle reverse order"
            onclick={onReverseToggle}
          >
            <ArrowDownUp class="size-4" />
          </Toggle>

          {#if hasActiveFilters}
            <Button
              variant="ghost"
              class="kz-toolbar-icon-button"
              onclick={() => navigateWithParams({
                priority: DEFAULT_PRIORITY_FILTER,
                q: "",
                sort: DEFAULT_SORT_KEY,
                reverse: DEFAULT_REVERSE
              })}
              aria-label="Reset filters"
            >
              <X class="size-4" />
            </Button>
          {/if}
        </div>
      </div>
    </div>
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
    <div class="kz-table-shell">
      <div class="kz-table-wrap">
          <table class="kz-table">
          <colgroup>
            <col class="w-[184px]" />
            <col class="w-[290px]" />
            <col class="w-[176px]" />
            <col class="w-[350px]" />
            <col />
            <col class="w-[130px]" />
            <col class="w-[165px]" />
          </colgroup>
          <thead class="bg-muted/25">
            <tr>
              <th class="kz-th">Poster</th>
              <th class="kz-th">Title</th>
              <th class="kz-th">Facts</th>
              <th class="kz-th">People & meta</th>
              <th class="kz-th">Plot</th>
              <th class="kz-th">Translate</th>
              <th class="kz-th">Actions</th>
            </tr>
          </thead>
          <tbody>
            {#each movies as movie (movie.id)}
              <tr class={`kz-row ${movie.kinorium_partial_match ? "kz-row--partial" : ""} ${isRowLeaving(movie.id) ? "kz-row--leaving" : ""}`}>
                <td class="kz-cell">
                  <KinozalPoster
                    src={movie.poster_url}
                    alt={`Poster of ${movie.title}`}
                    containerClass="kz-poster"
                  />
                </td>
                <td class="kz-cell">
                  <div class="kz-title-block">
                    <div class="kz-title-stack">
                      <p class="kz-title">{movie.title}</p>
                      <p class="kz-subtitle">{movie.original_title || "—"}</p>
                    </div>

                    <div class="kz-pill-row">
                      <span class={`kz-status-pill ${priorityToneMap[movie.priority_key] ?? "border border-border bg-muted text-muted-foreground"}`}>
                        {movie.priority_label}
                      </span>
                      {#if movie.kinorium_partial_match}
                        <span class="kz-status-pill kz-status-pill--warning">
                          Partial match
                        </span>
                      {/if}
                    </div>

                    <div class="flex items-center gap-1.5 pt-1">
                      <a
                        href={getKinoriumUrl(movie)}
                        target="_blank"
                        rel="noreferrer"
                        class="inline-flex items-center justify-center rounded px-2.5 py-1 text-xs font-semibold tracking-wide bg-teal-500/10 text-teal-600 hover:bg-teal-500/20 dark:text-teal-400 dark:bg-teal-400/10 transition-colors"
                        title="Search on Kinorium"
                      >
                        KR
                      </a>
                      <a
                        href={getTmdbUrl(movie)}
                        target="_blank"
                        rel="noreferrer"
                        class="inline-flex items-center justify-center rounded px-2.5 py-1 text-xs font-semibold tracking-wide bg-sky-500/10 text-sky-600 hover:bg-sky-500/20 dark:text-sky-400 dark:bg-sky-400/10 transition-colors"
                        title="Search on TMDB"
                      >
                        TMDB
                      </a>
                      <a
                        href={getImdbUrl(movie)}
                        target="_blank"
                        rel="noreferrer"
                        class="inline-flex items-center justify-center rounded px-2.5 py-1 text-xs font-semibold tracking-wide bg-amber-500/10 text-amber-600 hover:bg-amber-500/20 dark:text-amber-400 dark:bg-amber-400/10 transition-colors"
                        title={movie.imdb_id ? `View on IMDB (${movie.imdb_id})` : "Search on IMDB"}
                      >
                        IMDB
                      </a>
                      <a
                        href={getKinopoiskUrl(movie)}
                        target="_blank"
                        rel="noreferrer"
                        class="inline-flex items-center justify-center rounded px-2.5 py-1 text-xs font-semibold tracking-wide bg-orange-500/10 text-orange-600 hover:bg-orange-500/20 dark:text-orange-400 dark:bg-orange-400/10 transition-colors"
                        title={movie.kinopoisk_id ? `View on Kinopoisk (${movie.kinopoisk_id})` : "Search on Kinopoisk"}
                      >
                        KP
                      </a>
                    </div>

                    <p class="kz-meta-line">ID {movie.kinozal_id}</p>
                  </div>
                </td>
                <td class="kz-cell">
                  <dl class="kz-facts">
                    <div class="kz-fact">
                      <dt class="kz-fact-label">Year</dt>
                      <dd class="kz-fact-value">{movie.year}</dd>
                    </div>
                    <div class="kz-fact">
                      <dt class="kz-fact-label">IMDB</dt>
                      <dd class="kz-fact-value">{formatRating(movie.imdb_rating)}</dd>
                    </div>
                    <div class="kz-fact">
                      <dt class="kz-fact-label">KP</dt>
                      <dd class="kz-fact-value">{formatRating(movie.kinopoisk_rating)}</dd>
                    </div>
                    <div class="kz-fact">
                      <dt class="kz-fact-label">Scan</dt>
                      <dd class="kz-fact-value">{formatScanDate(movie.date_added)}</dd>
                    </div>
                  </dl>
                </td>
                <td class="kz-cell">
                  <div class="kz-meta-stack">
                    <div class="kz-meta-group">
                      <span class="kz-meta-label kz-meta-label--inline">Genres</span>
                      {#if compactList(movie.genres, 8).length}
                        {#each compactList(movie.genres, 8) as genre (genre)}
                          <span class="kz-meta-tag">{genre}</span>
                        {/each}
                      {:else}
                        <span class="kz-meta-empty">—</span>
                      {/if}
                    </div>

                    <div class="kz-meta-group">
                      <span class="kz-meta-label kz-meta-label--inline">Countries</span>
                      {#if compactList(movie.countries, 6).length}
                        {#each compactList(movie.countries, 6) as country (country)}
                          <span class="kz-meta-tag">{country}</span>
                        {/each}
                      {:else}
                        <span class="kz-meta-empty">—</span>
                      {/if}
                    </div>

                    <div class="kz-meta-group">
                      <span class="kz-meta-label kz-meta-label--inline">Director</span>
                      {#if compactList(movie.directors, 4).length}
                        {#each compactList(movie.directors, 4) as director (director)}
                          <span class="kz-meta-tag">{director}</span>
                        {/each}
                      {:else}
                        <span class="kz-meta-empty">—</span>
                      {/if}
                    </div>

                    <div class="kz-meta-group">
                      <span class="kz-meta-label kz-meta-label--inline">Actors</span>
                      {#if compactList(movie.actors, 6).length}
                        {#each compactList(movie.actors, 6) as actor (actor)}
                          <span class="kz-meta-tag">{actor}</span>
                        {/each}
                      {:else}
                        <span class="kz-meta-empty">—</span>
                      {/if}
                    </div>
                  </div>
                </td>
                <td class="kz-cell">
                  <p class="kz-plot [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:10] overflow-hidden">
                    {movie.plot || "—"}
                  </p>
                </td>
                <td class="kz-cell">
                  <p class="kz-translate">{movie.translate || "—"}</p>
                </td>
                <td class="kz-cell">
                  <div class="kz-actions">
                    <Button
                      href={movie.open_url ?? undefined}
                      target="_blank"
                      rel="noreferrer"
                      variant="outline"
                      size="sm"
                      class="kz-action-button"
                      disabled={!movie.open_url}
                    >
                      <ExternalLink class="mr-2 size-4" />
                      Open
                    </Button>

                    <Button
                      variant="outline"
                      size="sm"
                      class="kz-action-button bg-chart-3 text-white hover:opacity-90 dark:text-white"
                      onclick={() => openDownloadDialog(movie)}
                      disabled={loadingDownloadMovieId === movie.id}
                    >
                      <ArrowDownToLine class="mr-2 size-4" />
                      {loadingDownloadMovieId === movie.id ? "..." : "Download"}
                    </Button>

                    <Button
                      variant="outline"
                      size="sm"
                      class="kz-action-button"
                      onclick={() => performMovieAction(movie, "defer", "DEFER")}
                      disabled={isActionPending(movie.id, "defer")}
                    >
                      <Clock3 class="mr-2 size-4" />
                      {isActionPending(movie.id, "defer") ? "..." : "Defer"}
                    </Button>

                    <Button
                      variant="outline"
                      size="sm"
                      class="kz-action-button"
                      onclick={() => performMovieAction(movie, "wait-trans", "WAIT_TRANS")}
                      disabled={isActionPending(movie.id, "wait-trans")}
                    >
                      <Languages class="mr-2 size-4" />
                      {isActionPending(movie.id, "wait-trans") ? "..." : "Wait trans"}
                    </Button>

                    <Button
                      variant="outline"
                      size="sm"
                      class="kz-action-button kz-action-button--hide"
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
    </div>

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
  <Dialog.Content class="sm:max-w-[1320px]">
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
        <table class="w-full min-w-[980px] table-fixed border-collapse text-sm">
          <colgroup>
            <col class="w-[620px]" />
            <col class="w-[82px]" />
            <col class="w-[64px]" />
            <col class="w-[64px]" />
            <col class="w-[92px]" />
            <col class="w-[98px]" />
          </colgroup>
          <thead class="bg-muted/50">
            <tr class="text-left">
              <th class="px-2.5 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Title</th>
              <th class="px-2.5 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Size</th>
              <th class="px-2.5 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Seed</th>
              <th class="px-2.5 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Peer</th>
              <th class="px-2.5 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Created</th>
              <th class="px-2.5 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Down</th>
            </tr>
          </thead>
          <tbody>
            {#each downloadOptions as option (option.id)}
              <tr class="border-t align-top">
                <td class="px-2.5 py-2.5">
                  <div class="space-y-1">
                    <div class="text-sm leading-5 font-medium">
                      {#if option.is_4k}
                        <BootstrapBadge4kFill class="mr-1 inline-block size-3.5 align-[-0.15em] text-foreground/80" />
                      {/if}
                      {#if option.is_sdr}
                        <BootstrapBadgeSdFill class="mr-1 inline-block size-3.5 align-[-0.15em] text-foreground/80" />
                      {/if}
                      <a
                        href={option.link}
                        target="_blank"
                        rel="noreferrer"
                        class="kz-download-title-link"
                      >
                        {option.header}
                      </a>
                    </div>
                  </div>
                </td>
                <td class="px-2.5 py-2.5 text-xs">{option.size}</td>
                <td class="px-2.5 py-2.5 text-xs">{option.seed}</td>
                <td class="px-2.5 py-2.5 text-xs">{option.peer}</td>
                <td class="px-2.5 py-2.5 text-xs">{formatCreatedDate(option.created)}</td>
                <td class="px-2.5 py-2.5">
                  <div class="flex">
                    <Button
                      variant="default"
                      size="sm"
                      class="h-7 px-2.5 text-xs"
                      onclick={() => downloadTorrent(option.id)}
                      disabled={downloadingTorrentId === option.id}
                    >
                      {#if downloadingTorrentId === option.id}
                        <CircleDashed class="size-3.5 animate-spin" />
                      {:else}
                        Down
                      {/if}
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
