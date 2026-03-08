<script lang="ts">
  import { goto } from "$app/navigation";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Badge } from "$lib/components/ui/badge";
  import { Input } from "$lib/components/ui/input";
  import { Button } from "$lib/components/ui/button";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import { ArrowDownAZ, ArrowDownWideNarrow, ArrowUpAZ, ArrowUpDown, ArrowUpWideNarrow } from "@lucide/svelte";

  let { data } = $props();
  let hoveredMovie = $state<{
    title: string;
    original_title: string | null;
    year: number | null;
  } | null>(null);
  let tooltipX = $state(0);
  let tooltipY = $state(0);
  let searchQuery = $state("");
  let debounceHandle = $state<ReturnType<typeof setTimeout> | null>(null);
  let activeOrder = $state("-year");

  const orderOptions = [
    { field: "year", label: "По году" },
    { field: "imdb_rating", label: "По рейтингу" },
    { field: "title", label: "По названию" },
    { field: "added_at", label: "По дате добавления" }
  ];

  $effect(() => {
    searchQuery = data.activeQuery ?? "";
    activeOrder = data.activeOrder ?? "-year";
  });

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

  const getOrderField = (value: string) => value.replace(/^-/, "");
  const getOrderDirection = (value: string) => (value.startsWith("-") ? "desc" : "asc");
  const buildOrderValue = (field: string, direction: "asc" | "desc") =>
    direction === "desc" ? `-${field}` : field;
  const toggleOrderDirection = async () => {
    const currentField = getOrderField(activeOrder || "-year");
    const nextDirection = getOrderDirection(activeOrder || "-year") === "desc" ? "asc" : "desc";
    await applyOrder(buildOrderValue(currentField, nextDirection));
  };
  const activeOrderField = $derived(getOrderField(activeOrder || "-year"));
  const activeOrderDirection = $derived(getOrderDirection(activeOrder || "-year"));

  const onSearchInput = () => {
    if (debounceHandle) {
      clearTimeout(debounceHandle);
    }
    debounceHandle = setTimeout(() => {
      void applySearch(searchQuery);
    }, 250);
  };
</script>

<div class="mx-auto w-full max-w-6xl p-6">
  <div class="mb-6 space-y-3">
    <div class="flex items-center gap-3">
      <Input
        bind:value={searchQuery}
        type="search"
        placeholder="Поиск фильмов..."
        class="h-11 w-full"
        oninput={onSearchInput}
      />
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
              <Badge variant="secondary" class="absolute bottom-2 left-1/2 z-10 -translate-x-1/2 text-[10px] px-1.5 py-0.5">
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
