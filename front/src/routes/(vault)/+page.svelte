<script lang="ts">
  import { goto } from "$app/navigation";
  import { tick } from "svelte";
  import { toast } from "svelte-sonner";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Badge } from "$lib/components/ui/badge";
  import { Input } from "$lib/components/ui/input";
  import { Button } from "$lib/components/ui/button";
  import * as Dialog from "$lib/components/ui/dialog";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import { ArrowDownWideNarrow, ArrowUpDown, ArrowUpWideNarrow, Eye, Heart, Plus } from "@lucide/svelte";

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

  const orderOptions = [
    { field: "year", label: "По году" },
    { field: "imdb_rating", label: "По рейтингу" },
    { field: "title", label: "По названию" },
    { field: "added_at", label: "По дате добавления" }
  ];

  const getOrderField = (value: string) => value.replace(/^-/, "");
  const getOrderDirection = (value: string) => (value.startsWith("-") ? "desc" : "asc");
  const buildOrderValue = (field: string, direction: "asc" | "desc") =>
    direction === "desc" ? `-${field}` : field;
  const buildTmdbSelectionKey = (candidate: Pick<TmdbSearchResult, "media_type" | "tmdb_id">) =>
    `${candidate.media_type}:${candidate.tmdb_id}`;

  $effect(() => {
    searchQuery = data.activeQuery ?? "";
    activeOrder = data.activeOrder ?? "-year";
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

  const trimmedTmdbSearchQuery = $derived(tmdbSearchQuery.trim());
  const activeOrderField = $derived(getOrderField(activeOrder || "-year"));
  const activeOrderDirection = $derived(getOrderDirection(activeOrder || "-year"));
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

  const toggleOrderDirection = async () => {
    const currentField = getOrderField(activeOrder || "-year");
    const nextDirection = getOrderDirection(activeOrder || "-year") === "desc" ? "asc" : "desc";
    await applyOrder(buildOrderValue(currentField, nextDirection));
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
          <DropdownMenu.Root>
            <DropdownMenu.Trigger>
              {#snippet child({ props })}
                <Button {...props} variant="outline" class="h-11 min-w-[180px] justify-between">
                  {orderOptions.find((item) => item.field === activeOrderField)?.label ?? "Сортировка"}
                  <ArrowUpDown class="size-4" />
                </Button>
              {/snippet}
            </DropdownMenu.Trigger>
            <DropdownMenu.Content class="w-56" align="end">
              <DropdownMenu.RadioGroup
                value={activeOrderField}
                onValueChange={(value) => applyOrder(buildOrderValue(value, activeOrderDirection))}
              >
                {#each orderOptions as item (item.field)}
                  <DropdownMenu.RadioItem value={item.field}>
                    {item.label}
                  </DropdownMenu.RadioItem>
                {/each}
              </DropdownMenu.RadioGroup>
            </DropdownMenu.Content>
          </DropdownMenu.Root>

          <Button variant="outline" class="h-11 min-w-[96px]" onclick={toggleOrderDirection}>
            {#if activeOrderDirection === "desc"}
              <ArrowDownWideNarrow class="size-4" />
              DESC
            {:else}
              <ArrowUpWideNarrow class="size-4" />
              ASC
            {/if}
          </Button>

          <Button class="h-11 min-w-[132px]" onclick={openAddMovieDialog}>
            <Plus class="size-4" />
            Add movie
          </Button>
        </div>
      </div>

      {#if data.activeGenre}
        <p class="text-muted-foreground text-sm">Фильтр по жанру: <strong>{data.activeGenre}</strong></p>
      {/if}
      {#if data.activeList}
        <p class="text-muted-foreground text-sm">Фильтр по списку: <strong>{data.activeList}</strong></p>
      {/if}
      {#if data.activeQuery}
        <p class="text-muted-foreground text-sm">Поиск: <strong>{data.activeQuery}</strong></p>
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
      <div class="flex flex-wrap gap-4">
        {#each data.movies as movie (movie.id)}
          <a
            href={`/movies/${movie.slug}`}
            data-sveltekit-preload-data="hover"
            class="block"
            onmouseenter={() => onMovieEnter(movie)}
            onmousemove={onMovieMove}
            onmouseleave={onMovieLeave}
          >
            <Card class="relative h-[270px] w-[180px] overflow-hidden rounded-md border !gap-0 !py-0 transition hover:shadow-md">
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
      </div>

      {#if hoveredMovie}
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

      {#if data.movies.length === 0}
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
