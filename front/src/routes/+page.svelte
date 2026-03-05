<script lang="ts">
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Button } from "$lib/components/ui/button";
  import { Badge } from "$lib/components/ui/badge";

  let { data } = $props();
</script>

<div class="mx-auto w-full max-w-6xl p-6">
  <div class="mb-6 space-y-2">
    <h1 class="text-2xl font-semibold">Vault Movies API Test</h1>
    <p class="text-muted-foreground text-sm">
      Первое соединение Svelte фронта с Django backend через django-ninja.
    </p>
  </div>

  {#if data.apiError}
    <Card>
      <CardHeader>
        <CardTitle>Ошибка API</CardTitle>
        <CardDescription>{data.apiError}</CardDescription>
      </CardHeader>
    </Card>
  {:else}
    <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {#each data.movies as movie (movie.id)}
        <Card>
          <CardHeader>
            <CardTitle class="flex items-center justify-between gap-2">
              <span class="truncate">{movie.title}</span>
              <Badge variant="secondary">{movie.year ?? "?"}</Badge>
            </CardTitle>
            <CardDescription class="truncate">
              {movie.original_title || "No original title"}
            </CardDescription>
          </CardHeader>
          <CardContent class="flex items-center justify-between gap-2">
            <p class="text-muted-foreground text-sm">slug: {movie.slug}</p>
            <Button size="sm" variant="outline">Open</Button>
          </CardContent>
        </Card>
      {/each}
    </div>

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
