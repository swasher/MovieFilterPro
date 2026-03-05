<script lang="ts">
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Badge } from "$lib/components/ui/badge";

  let { data } = $props();
  let hoveredMovie = $state<{
    title: string;
    original_title: string | null;
    year: number | null;
  } | null>(null);
  let tooltipX = $state(0);
  let tooltipY = $state(0);

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
</script>

<div class="mx-auto w-full max-w-6xl p-6">
  <div class="mb-6 space-y-2">
    <h1 class="text-2xl font-semibold">Vault Movies API Test</h1>
    <p class="text-muted-foreground text-sm">
      Первое соединение Svelte фронта с Django backend через django-ninja.
    </p>
    {#if data.activeGenre}
      <p class="text-muted-foreground text-sm">Фильтр по жанру: <strong>{data.activeGenre}</strong></p>
    {/if}
    {#if data.activeStatus}
      <p class="text-muted-foreground text-sm">Фильтр по статусу: <strong>{data.activeStatus}</strong></p>
    {/if}
    {#if data.activeList}
      <p class="text-muted-foreground text-sm">Фильтр по списку: <strong>{data.activeList}</strong></p>
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
        class="bg-foreground text-background pointer-events-none fixed z-50 max-w-xs rounded-md px-3 py-2 text-xs shadow-lg"
        style={`left:${tooltipX}px; top:${tooltipY}px;`}
      >
        <p>{hoveredMovie.title}</p>
        <p>{hoveredMovie.original_title || "—"}</p>
        <p>{hoveredMovie.year ?? "—"}</p>
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
