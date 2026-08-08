<script lang="ts">
  import { goto } from "$app/navigation";
  import { tick } from "svelte";
  import { toast } from "svelte-sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
import { Badge } from "$lib/components/ui/badge";
import { Input } from "$lib/components/ui/input";
import { Button } from "$lib/components/ui/button";
import * as Dialog from "$lib/components/ui/dialog";
import * as ToggleGroup from "$lib/components/ui/toggle-group";
import { SortSelect } from "$lib/components/ui/sort-select";
import { LayoutGrid, TextAlignJustify, Eye, Heart, Plus, Filter, RotateCcw } from "@lucide/svelte";

type MovieCard = {
  id: number;
  title: string;
  original_title: string | null;
  year: number | null;
  slug: string;
  poster_url: string | null;
  movie_type: string | null;
  in_watched: boolean;
  in_favorites: boolean;
};

type Genre = {
  name: string;
  slug: string;
};

type TmdbSearchResult = {
    tmdb_id: number;
    media_type: string;
    title: string;
    original_title: string;
    year: number | null;
    score: number;
    score_reasons: string[];
    poster_url: string | null;
    popularity: number | null;
    vote_average: number | null;
  };

  let { data } = $props();
  let hoveredMovie = $state<{
    title: string;
    original_title: string | null;
    year: number | null;
  } | null>(null);
  let tooltipX = $state(0);
  let tooltipY = $state(0);
  let searchQuery = $state("");
  let searchDebounceHandle = $state<ReturnType<typeof setTimeout> | null>(null);
  let activeOrder = $state("-year");
  let isListView = $state(false);

// Infinite scroll state
  let allMovies = $state<MovieCard[]>(data.movies ?? []);
  let currentOffset = $state(data.initialOffset ?? 0);
  let isLoadingMore = $state(false);
  let hasMore = $state((data.movies ?? []).length >= 30);
  let sentinelRef = $state<HTMLDivElement | null>(null);
  // Immediate guard for IntersectionObserver (runs before Svelte state updates)
  let loadingGuard = false;

  // Initialize allMovies when data.movies changes (e.g., after filter/search/sort)
  $effect(() => {
    allMovies = data.movies ?? [];
    currentOffset = data.initialOffset ?? 0;
    hasMore = (data.movies ?? []).length >= 30;
    loadingGuard = false;
  });

  let addMovieDialogOpen = $state(false);
  let tmdbSearchQuery = $state("");
  let tmdbSearchInputRef = $state<HTMLInputElement | null>(null);
  let tmdbSearchDebounceHandle = $state<ReturnType<typeof setTimeout> | null>(null);
  let tmdbSearchAbortController = $state<AbortController | null>(null);
  let isSearchingTmdb = $state(false);
  let isImportingTmdb = $state(false);
  let tmdbSearchPerformed = $state(false);
  let tmdbSearchError = $state("");
  let tmdbSearchResults = $state<TmdbSearchResult[]>([]);
  let selectedTmdbKey = $state<string | null>(null);

  let filterOpen = $state(false);
  let selectedGenres = $state<string[]>([]);
  let yearFrom = $state("");
  let yearTo = $state("");
  let selectedMovieType = $state("");
  let selectedWatchStatus = $state("");
  let isFavorite = $state(false);

  const genreNameMap = $derived(
    Object.fromEntries((data.genres ?? []).map((g) => [g.slug, g.name]))
  );

  const trimmedTmdbSearchQuery = $derived(tmdbSearchQuery.trim());

  $effect(() => {
    searchQuery = data.activeQuery ?? "";
    activeOrder = data.activeOrder ?? "-year";
  });

  $effect(() => {
    selectedGenres = data.activeGenre ?? [];
    yearFrom = data.activeYearFrom ?? "";
    yearTo = data.activeYearTo ?? "";
    selectedMovieType = data.activeMovieType ?? "";
    selectedWatchStatus = data.activeWatchStatus ?? "";
    isFavorite = data.activeIsFavorite ?? false;
  });

  $effect(() => {
    if (addMovieDialogOpen) {
      return;
    }

    if (tmdbSearchDebounceHandle) {
      clearTimeout(tmdbSearchDebounceHandle);
      tmdbSearchDebounceHandle = null;
    }
    tmdbSearchAbortController?.abort();
    tmdbSearchAbortController = null;
    tmdbSearchQuery = "";
    isSearchingTmdb = false;
    isImportingTmdb = false;
    tmdbSearchPerformed = false;
    tmdbSearchError = "";
    tmdbSearchResults = [];
    selectedTmdbKey = null;
  });

  $effect(() => {
    return () => {
      if (searchDebounceHandle) {
        clearTimeout(searchDebounceHandle);
      }
      if (tmdbSearchDebounceHandle) {
        clearTimeout(tmdbSearchDebounceHandle);
      }
      tmdbSearchAbortController?.abort();
    };
  });

  // Infinite scroll: IntersectionObserver on sentinel
  $effect(() => {
    const sentinel = sentinelRef;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry.isIntersecting && !loadingGuard && hasMore && !isLoadingMore) {
          loadingGuard = true;
          void loadMore();
        }
      },
      { rootMargin: "200px", threshold: 0.1 }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  });

  const loadMore = async () => {
    if (isLoadingMore || !hasMore) {
      loadingGuard = false;
      return;
    }
    isLoadingMore = true;
    loadingGuard = true;

    const nextOffset = currentOffset + 30;
    const params = new URLSearchParams(window.location.search);
    params.set("offset", nextOffset.toString());

    try {
      const response = await fetch(`/api/vault/movies?${params.toString()}`);
      if (!response.ok) {
        hasMore = false;
        return;
      }
      const newMovies: MovieCard[] = await response.json();
      if (newMovies.length === 0) {
        hasMore = false;
        return;
      }
      // Filter out any duplicates by ID (defensive: API might return overlapping results)
      const existingIds = new Set(allMovies.map(m => m.id));
      const uniqueNewMovies = newMovies.filter(m => !existingIds.has(m.id));
      if (uniqueNewMovies.length === 0) {
        hasMore = false;
        return;
      }
      allMovies = [...allMovies, ...uniqueNewMovies];
      currentOffset = nextOffset;
      hasMore = newMovies.length >= 30;
    } catch {
      hasMore = false;
    } finally {
      isLoadingMore = false;
      // Small delay to prevent immediate re-trigger from IntersectionObserver
      setTimeout(() => { loadingGuard = false; }, 100);
    }
  };

  const buildTmdbSelectionKey = (candidate: Pick<TmdbSearchResult, "media_type" | "tmdb_id">) =>
    `${candidate.media_type}:${candidate.tmdb_id}`;

  const selectedTmdbCandidate = $derived(
    tmdbSearchResults.find((item) => buildTmdbSelectionKey(item) === selectedTmdbKey) ?? null
  );

  const onMovieEnter = (movie: { title: string; original_title: string | null; year: number | null }) => {
    hoveredMovie = movie;
  };

  const onMovieMove = (event: MouseEvent) => {
    tooltipX = event.clientX + 12;
    tooltipY = event.clientY + 16;
  };

  const onMovieLeave = () => {
    hoveredMovie = null;
  };

  const handleUnauthorized = async (status: number, message?: string) => {
    if (status !== 401) {
      return false;
    }

    addMovieDialogOpen = false;
    toast.error(message ?? "Нужно войти в систему.");
    await goto("/login");
    return true;
  };

  const applySearch = async (value: string) => {
    const params = new URLSearchParams(window.location.search);
    const trimmedValue = value.trim();

    if (trimmedValue) {
      params.set("q", trimmedValue);
    } else {
      params.delete("q");
    }

    const queryString = params.toString();
    await goto(queryString ? `/?${queryString}` : "/", {
      replaceState: true,
      keepFocus: true,
      noScroll: true,
      invalidateAll: true
    });
  };

  const applyOrder = async (value: string) => {
    const params = new URLSearchParams(window.location.search);

    if (value && value !== "-year") {
      params.set("order", value);
    } else {
      params.delete("order");
    }

    const queryString = params.toString();
    activeOrder = value;
    await goto(queryString ? `/?${queryString}` : "/", {
      replaceState: true,
      keepFocus: true,
      noScroll: true,
      invalidateAll: true
    });
  };

  const applyFilters = async () => {
    const params = new URLSearchParams(window.location.search);

    params.delete("genre");
    if (selectedGenres.length > 0) params.set("genre", selectedGenres.join(","));

    if (yearFrom) params.set("year_from", yearFrom); else params.delete("year_from");
    if (yearTo) params.set("year_to", yearTo); else params.delete("year_to");
    if (selectedMovieType) params.set("movie_type", selectedMovieType); else params.delete("movie_type");
    if (selectedWatchStatus) params.set("watch_status", selectedWatchStatus); else params.delete("watch_status");
    if (isFavorite) params.set("is_favorite", "true"); else params.delete("is_favorite");

    params.delete("page");

    const queryString = params.toString();
    await goto(queryString ? `/?${queryString}` : "/", {
      replaceState: true, keepFocus: true, noScroll: true, invalidateAll: true
    });
    filterOpen = false;
  };

  const resetFilters = async () => {
    selectedGenres = [];
    yearFrom = "";
    yearTo = "";
    selectedMovieType = "";
    selectedWatchStatus = "";
    isFavorite = false;
    await applyFilters();
  };

  const onSearchInput = () => {
    if (searchDebounceHandle) {
      clearTimeout(searchDebounceHandle);
    }
    searchDebounceHandle = setTimeout(() => {
      void applySearch(searchQuery);
    }, 250);
  };

  const openAddMovieDialog = async () => {
    addMovieDialogOpen = true;
    await tick();
    tmdbSearchInputRef?.focus();
  };

  const searchTmdbMovies = async (query: string) => {
    if (tmdbSearchAbortController) {
      tmdbSearchAbortController.abort();
    }

    const controller = new AbortController();
    tmdbSearchAbortController = controller;
    isSearchingTmdb = true;
    tmdbSearchPerformed = true;
    tmdbSearchError = "";

    try {
      const params = new URLSearchParams({
        q: query,
        limit: "10"
      });
      const response = await fetch(`/api/vault/tmdb/search?${params.toString()}`, {
        signal: controller.signal
      });
      const payload = (await response.json()) as {
        results?: TmdbSearchResult[];
        message?: string;
      };

      if (!response.ok) {
        if (await handleUnauthorized(response.status, payload.message)) {
          return;
        }
        tmdbSearchResults = [];
        selectedTmdbKey = null;
        tmdbSearchError = payload.message ?? `HTTP ${response.status}`;
        return;
      }

      tmdbSearchResults = payload.results ?? [];
      selectedTmdbKey = tmdbSearchResults[0] ? buildTmdbSelectionKey(tmdbSearchResults[0]) : null;
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      tmdbSearchResults = [];
      selectedTmdbKey = null;
      tmdbSearchError = error instanceof Error ? error.message : "Не удалось выполнить поиск TMDB";
    } finally {
      if (tmdbSearchAbortController === controller) {
        tmdbSearchAbortController = null;
      }
      isSearchingTmdb = false;
    }
  };

  const onTmdbSearchInput = () => {
    if (tmdbSearchDebounceHandle) {
      clearTimeout(tmdbSearchDebounceHandle);
      tmdbSearchDebounceHandle = null;
    }

    tmdbSearchAbortController?.abort();
    tmdbSearchAbortController = null;
    tmdbSearchError = "";

    if (trimmedTmdbSearchQuery.length < 2) {
      isSearchingTmdb = false;
      tmdbSearchPerformed = false;
      tmdbSearchResults = [];
      selectedTmdbKey = null;
      return;
    }

    tmdbSearchDebounceHandle = setTimeout(() => {
      void searchTmdbMovies(trimmedTmdbSearchQuery);
    }, 350);
  };

  const importSelectedTmdbMovie = async () => {
    if (!selectedTmdbCandidate) {
      toast.error("Выбери фильм для добавления.");
      return;
    }

    isImportingTmdb = true;

    try {
      const response = await fetch("/api/vault/tmdb/import", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          tmdb_id: selectedTmdbCandidate.tmdb_id,
          media_type: selectedTmdbCandidate.media_type
        })
      });
      const payload = (await response.json()) as {
        status?: string;
        message?: string;
        created?: boolean;
        movie?: MovieCard | null;
      };

      if (!response.ok) {
        if (await handleUnauthorized(response.status, payload.message)) {
          return;
        }
        toast.error(payload.message ?? `HTTP ${response.status}`);
        return;
      }

      if (!payload.movie?.slug) {
        toast.error(payload.message ?? "Не удалось определить карточку фильма.");
        return;
      }

      addMovieDialogOpen = false;
      toast.success(payload.message ?? (payload.created ? "Фильм добавлен в Vault." : "Фильм уже есть в Vault."));
      await goto(`/movies/${payload.movie.slug}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось добавить фильм в Vault");
    } finally {
      isImportingTmdb = false;
    }
  };
</script>

<div class="mx-auto w-full max-w-6xl p-6">
  <div class="mx-auto w-full max-w-[964px]">
    <div class="mb-6 space-y-3">
      <div class="flex flex-wrap items-center gap-3">
        <Input
          bind:value={searchQuery}
          type="search"
          placeholder="Поиск фильмов..."
          class="h-11 min-w-[260px] flex-1"
          oninput={onSearchInput}
        />

        <div class="flex flex-wrap items-center gap-3">
          <SortSelect value={activeOrder} onChange={applyOrder} />

          <Button
            variant="outline"
            size="icon"
            class="h-11 w-11"
            onclick={() => (isListView = !isListView)}
            aria-label="Toggle view mode"
          >
            {#if isListView}
              <TextAlignJustify class="size-4 text-foreground" />
            {:else}
              <LayoutGrid class="size-4 text-muted-foreground" />
            {/if}
          </Button>

          <Button
            variant="outline"
            class="h-11"
            onclick={() => (filterOpen = true)}
          >
            <Filter class="size-4" />
            Фильтр
          </Button>

          <Button class="h-11 min-w-[132px]" onclick={openAddMovieDialog}>
            <Plus class="size-4" />
            Add movie
          </Button>
        </div>
      </div>

      {#if selectedGenres.length > 0 || yearFrom || yearTo || selectedMovieType || selectedWatchStatus || isFavorite || data.activeQuery}
        <div class="flex flex-wrap items-center gap-3 text-sm">
          {#if selectedGenres.length > 0}
            <p class="text-muted-foreground">
              Жанр: {selectedGenres.map((g) => genreNameMap[g] ?? g).join(", ")}
              <button class="underline hover:text-foreground" onclick={() => { selectedGenres = []; applyFilters(); }}>×</button>
            </p>
          {/if}
          {#if yearFrom || yearTo}
            <span class="text-border">|</span>
            <p class="text-muted-foreground">
              Год: {yearFrom || "?"}–{yearTo || "?"}
              <button class="underline hover:text-foreground" onclick={() => { yearFrom = ""; yearTo = ""; applyFilters(); }}>×</button>
            </p>
          {/if}
          {#if selectedMovieType}
            <span class="text-border">|</span>
            <p class="text-muted-foreground">
              Тип: {selectedMovieType}
              <button class="underline hover:text-foreground" onclick={() => { selectedMovieType = ""; applyFilters(); }}>×</button>
            </p>
          {/if}
          {#if selectedWatchStatus}
            <span class="text-border">|</span>
            <p class="text-muted-foreground">
              Просмотрено: {selectedWatchStatus === "watched" ? "Да" : "Нет"}
              <button class="underline hover:text-foreground" onclick={() => { selectedWatchStatus = ""; applyFilters(); }}>×</button>
            </p>
          {/if}
          {#if isFavorite}
            <span class="text-border">|</span>
            <p class="text-muted-foreground">
              Только избранное
              <button class="underline hover:text-foreground" onclick={() => { isFavorite = false; applyFilters(); }}>×</button>
            </p>
          {/if}
          {#if data.activeQuery}
            <span class="text-border">|</span>
            <p class="text-muted-foreground">Поиск: <strong>{data.activeQuery}</strong></p>
          {/if}
        </div>
      {/if}
    </div>

    {#if data.apiError}
      <Card>
        <CardHeader>
          <CardTitle>Ошибка API</CardTitle>
          <CardDescription>{data.apiError}</CardDescription>
        </CardHeader>
      </Card>
    {:else}
      {#if isListView}
        <div class="rounded-md border">
          <table class="w-full table-fixed text-sm">
            <thead class="bg-muted/60 sticky top-0 z-10 border-b backdrop-blur">
              <tr>
                <th class="w-14 px-2 py-2 font-medium">Poster</th>
                <th class="px-3 py-2 font-medium">Title</th>
                <th class="px-3 py-2 font-medium">Original title</th>
                <th class="w-20 px-3 py-2 font-medium">Year</th>
                <th class="w-20 px-3 py-2 font-medium">Type</th>
                <th class="w-28 px-3 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {#each allMovies as movie (movie.id)}
                <tr
                  class="border-b last:border-b-0 transition hover:bg-accent/20"
                >
                  <td class="px-2 py-2 align-middle">
                    <a href={`/movies/${movie.slug}`} data-sveltekit-preload-data="hover">
                      {#if movie.poster_url}
                        <img
                          src={movie.poster_url}
                          alt={movie.title}
                          class="h-12 w-8 object-cover rounded"
                          loading="lazy"
                        />
                      {:else}
                        <div class="bg-muted text-muted-foreground flex h-12 w-8 items-center justify-center text-[10px]">
                          no
                        </div>
                      {/if}
                    </a>
                  </td>
                  <td class="px-3 py-2 align-middle font-medium">
                    <a href={`/movies/${movie.slug}`} data-sveltekit-preload-data="hover">
                      {movie.title}
                    </a>
                  </td>
                  <td class="text-muted-foreground px-3 py-2 align-middle">
                    {movie.original_title || "—"}
                  </td>
                  <td class="px-3 py-2 align-middle">{movie.year ?? "—"}</td>
                  <td class="px-3 py-2 align-middle">
                    {#if movie.movie_type === "series"}
                      <Badge variant="secondary" class="px-1.5 py-0.5 text-[10px]">SERIES</Badge>
                    {:else}
                      <Badge variant="secondary" class="px-1.5 py-0.5 text-[10px]">MOVIE</Badge>
                    {/if}
                  </td>
                  <td class="px-3 py-2 align-middle flex items-center gap-1.5">
                    {#if movie.in_favorites}
                      <Badge variant="secondary" class="px-1.5 py-0.5 text-[10px]" title="Любимое">
                        <Heart class="h-3 w-3 text-red-500" />
                      </Badge>
                    {/if}
                    {#if movie.in_watched}
                      <Badge variant="secondary" class="px-1.5 py-0.5 text-[10px]" title="Просмотрено">
                        <Eye class="h-3 w-3" />
                      </Badge>
                    {/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
          {#if hasMore || isLoadingMore}
            <div bind:this={sentinelRef} class="h-8 flex items-center justify-center">
              {#if isLoadingMore}
                <div class="flex items-center gap-2 text-sm text-muted-foreground">
                  <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/></svg>
                  Загрузка...
                </div>
              {:else}
                <div class="text-sm text-muted-foreground">Прокрутите для загрузки ещё</div>
              {/if}
            </div>
          {/if}
        </div>
      {:else}
        <div class="flex flex-wrap gap-4">
          {#each allMovies as movie (movie.id)}
            <a
              href={`/movies/${movie.slug}`}
              data-sveltekit-preload-data="hover"
              class="block"
              onmouseenter={() => onMovieEnter(movie)}
              onmousemove={onMovieMove}
              onmouseleave={onMovieLeave}
            >
              <Card class="relative h-[270px] w-[180px] flex-none overflow-hidden rounded-md border !gap-0 !py-0 transition hover:shadow-md">
                <CardContent class="h-full !p-0">
                  {#if movie.movie_type === "series"}
                    <Badge variant="secondary" class="absolute left-2 top-2 z-10 px-1.5 py-0.5 text-[10px]">SERIES</Badge>
                  {/if}

                  <div class="absolute bottom-2 left-2 right-2 z-10 flex items-center justify-between">
                    {#if movie.in_favorites && data.activeStatus !== "favorites"}
                      <Badge variant="secondary" class="px-1.5 py-0.5 text-[10px]" title="Любимое">
                        <Heart class="h-3 w-3 text-red-500" />
                      </Badge>
                    {/if}
                    {#if movie.in_watched && data.activeStatus !== "watched"}
                      <Badge variant="secondary" class="px-1.5 py-0.5 text-[10px]" title="Просмотрено">
                        <Eye class="h-3 w-3" />
                      </Badge>
                    {/if}
                  </div>

                  <Badge variant="secondary" class="absolute bottom-2 left-1/2 z-10 -translate-x-1/2 px-1.5 py-0.5 text-[10px]">
                    {movie.year ?? "?"}
                  </Badge>

                  {#if movie.poster_url}
                    <img
                      src={movie.poster_url}
                      alt={movie.title}
                      class="h-full w-full object-cover"
                      loading="lazy"
                    />
                  {:else}
                    <div class="bg-muted text-muted-foreground flex h-full w-full items-center justify-center text-xs">
                      no poster
                    </div>
                  {/if}
                </CardContent>
              </Card>
            </a>
          {/each}
          {#if hasMore || isLoadingMore}
            <div bind:this={sentinelRef} class="w-full h-8 flex items-center justify-center">
              {#if isLoadingMore}
                <div class="flex items-center gap-2 text-sm text-muted-foreground">
                  <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/></svg>
                  Загрузка...
                </div>
              {:else}
                <div class="text-sm text-muted-foreground">Прокрутите для загрузки ещё</div>
              {/if}
            </div>
          {/if}
        </div>
      {/if}

      {#if hoveredMovie && !isListView}
        <div
          class="bg-popover text-popover-foreground pointer-events-none fixed z-50 max-w-[220px] rounded-lg border border-border/70 px-3 py-2.5 shadow-lg backdrop-blur-sm"
          style={`left:${tooltipX}px; top:${tooltipY}px;`}
        >
          <p class="line-clamp-2 text-sm font-semibold leading-tight">{hoveredMovie.title}</p>
          <p class="text-muted-foreground mt-1 line-clamp-2 text-[12px] leading-snug">
            {hoveredMovie.original_title || "—"}
          </p>
          <p class="text-muted-foreground mt-1 text-[11px] font-medium">
            {hoveredMovie.year ?? "—"}
          </p>
        </div>
      {/if}

      {#if allMovies.length === 0}
        <Card>
          <CardHeader>
            <CardTitle>Список пуст</CardTitle>
            <CardDescription>Эндпоинт отработал, но фильмов пока нет.</CardDescription>
          </CardHeader>
        </Card>
      {/if}
    {/if}
  </div>
</div>

<Dialog.Root bind:open={addMovieDialogOpen}>
  <Dialog.Content class="flex h-[80vh] max-h-[80vh] flex-col sm:max-w-5xl">
    <Dialog.Header>
      <Dialog.Title>Добавить фильм из TMDB</Dialog.Title>
      <Dialog.Description>
        Введи название, выбери подходящий результат и подтверди импорт в Vault.
      </Dialog.Description>
    </Dialog.Header>

    <div class="flex min-h-0 flex-1 flex-col space-y-4">
      <Input
        bind:ref={tmdbSearchInputRef}
        bind:value={tmdbSearchQuery}
        type="search"
        placeholder="Название фильма или сериала..."
        class="h-11"
        autofocus
        oninput={onTmdbSearchInput}
      />

      <div class="min-h-0 flex-1 overflow-hidden rounded-xl border">
        {#if trimmedTmdbSearchQuery.length < 2}
          <div class="text-muted-foreground flex h-full items-center justify-center text-sm">
            Введи минимум 2 символа для поиска на TMDB.
          </div>
        {:else if isSearchingTmdb}
          <div class="text-muted-foreground flex h-full items-center justify-center text-sm">
            Ищу результаты на TMDB...
          </div>
        {:else if tmdbSearchError}
          <div class="text-destructive flex h-full items-center justify-center px-4 text-center text-sm">
            {tmdbSearchError}
          </div>
        {:else if tmdbSearchResults.length}
          <div class="h-full overflow-auto">
            <table class="w-full table-fixed text-left text-sm">
              <thead class="bg-muted/60 sticky top-0 z-10 border-b backdrop-blur">
                <tr>
                  <th class="w-18 px-3 py-2 font-medium">Poster</th>
                  <th class="px-3 py-2 font-medium">Title</th>
                  <th class="px-3 py-2 font-medium">Original title</th>
                  <th class="w-20 px-3 py-2 font-medium">Year</th>
                  <th class="w-20 px-3 py-2 font-medium">Type</th>
                  <th class="w-24 px-3 py-2 font-medium">TMDB</th>
                </tr>
              </thead>
              <tbody>
                {#each tmdbSearchResults as candidate (buildTmdbSelectionKey(candidate))}
                  <tr
                    class={`cursor-pointer border-b transition last:border-b-0 ${
                      selectedTmdbKey === buildTmdbSelectionKey(candidate)
                        ? "bg-accent/40"
                        : "hover:bg-accent/20"
                    }`}
                    onclick={() => {
                      selectedTmdbKey = buildTmdbSelectionKey(candidate);
                    }}
                  >
                    <td class="px-3 py-2 align-middle">
                      <div class="bg-muted flex h-[72px] w-12 items-center justify-center overflow-hidden rounded-md">
                        {#if candidate.poster_url}
                          <img
                            src={candidate.poster_url}
                            alt={candidate.title}
                            class="h-full w-full object-cover"
                            loading="lazy"
                          />
                        {:else}
                          <span class="text-muted-foreground text-[9px]">none</span>
                        {/if}
                      </div>
                    </td>
                    <td class="px-3 py-2 align-middle">
                      <div class="truncate font-medium">{candidate.title}</div>
                    </td>
                    <td class="text-muted-foreground px-3 py-2 align-middle">
                      <div class="truncate">{candidate.original_title || "—"}</div>
                    </td>
                    <td class="px-3 py-2 align-middle">{candidate.year ?? "—"}</td>
                    <td class="px-3 py-2 align-middle">{candidate.media_type}</td>
                    <td class="px-3 py-2 align-middle">
                      {#if candidate.vote_average}
                        {candidate.vote_average.toFixed(1)}
                      {:else}
                        —
                      {/if}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else if tmdbSearchPerformed}
          <div class="text-muted-foreground flex h-full items-center justify-center text-sm">
            Ничего не найдено.
          </div>
        {/if}
      </div>
    </div>

    <Dialog.Footer>
      <Button variant="outline" onclick={() => {
        addMovieDialogOpen = false;
      }}>
        Отмена
      </Button>
      <Button onclick={importSelectedTmdbMovie} disabled={isImportingTmdb || !selectedTmdbCandidate}>
        {isImportingTmdb ? "Добавляю..." : "Add"}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={filterOpen}>
  <Dialog.Content class="sm:max-w-md">
    <Dialog.Header>
      <Dialog.Title>Фильтры</Dialog.Title>
      <Dialog.Description>Настрой фильтрацию списка фильмов.</Dialog.Description>
    </Dialog.Header>

    <div class="space-y-4 py-2">
      <div class="space-y-2">
        <p class="text-sm font-medium">Жанр</p>
        {#if data.genres}
          <div class="max-h-48 overflow-y-auto space-y-1 rounded-md border p-2">
            {#each data.genres as genre}
              <label class="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={selectedGenres.includes(genre.slug)}
                  onchange={() => {
                    if (selectedGenres.includes(genre.slug)) {
                      selectedGenres = selectedGenres.filter(g => g !== genre.slug);
                    } else {
                      selectedGenres = [...selectedGenres, genre.slug];
                    }
                  }}
                  class="rounded border-input"
                />
                {genre.name}
              </label>
            {/each}
          </div>
        {:else}
          <p class="text-muted-foreground text-sm">Загрузка жанров...</p>
        {/if}
      </div>

      <div class="space-y-2">
        <p class="text-sm font-medium">Год</p>
        <div class="flex items-center gap-2">
          <Input
            type="number"
            placeholder="от"
            bind:value={yearFrom}
            class="h-9 w-24"
            min="1800"
            max="2100"
          />
          <span class="text-muted-foreground">—</span>
          <Input
            type="number"
            placeholder="до"
            bind:value={yearTo}
            class="h-9 w-24"
            min="1800"
            max="2100"
          />
        </div>
      </div>

      <div class="space-y-2">
        <p class="text-sm font-medium">Тип</p>
        <ToggleGroup.Root type="single" value={selectedMovieType} onValueChange={(v) => selectedMovieType = v ?? ""}>
          <ToggleGroup.Item value="movie">Фильм</ToggleGroup.Item>
          <ToggleGroup.Item value="series">Сериал</ToggleGroup.Item>
          <ToggleGroup.Item value="">Не важно</ToggleGroup.Item>
        </ToggleGroup.Root>
      </div>

      <div class="space-y-2">
        <p class="text-sm font-medium">Просмотрено</p>
        <ToggleGroup.Root type="single" value={selectedWatchStatus} onValueChange={(v) => selectedWatchStatus = v ?? ""}>
          <ToggleGroup.Item value="watched">Просмотрено</ToggleGroup.Item>
          <ToggleGroup.Item value="not_watched">Не просмотрено</ToggleGroup.Item>
          <ToggleGroup.Item value="">Не важно</ToggleGroup.Item>
        </ToggleGroup.Root>
      </div>

      <div class="flex items-center gap-2">
        <input
          type="checkbox"
          checked={isFavorite}
          onchange={() => { isFavorite = !isFavorite; }}
          class="rounded border-input"
          id="filter-favorite"
        />
        <label for="filter-favorite" class="text-sm cursor-pointer">Только избранное</label>
      </div>
    </div>

    <Dialog.Footer>
      <Button variant="outline" onclick={resetFilters}>
        <RotateCcw class="size-4 mr-2" />
        Сбросить
      </Button>
      <Button onclick={applyFilters}>Применить</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
