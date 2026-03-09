<script lang="ts">
  import { Badge } from "$lib/components/ui/badge";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";

  type ConnectionEvent = {
    id: number;
    operation_id: string;
    created_at: string;
    source: string;
    event_type: string;
    level: string;
    message: string;
    rss_kinozal_id: number | null;
    torrent_kinozal_id: number | null;
    imdb_id: string | null;
    kinopoisk_id: number | null;
    tmdb_id: number | null;
    movie_rss_title: string | null;
    vault_movie: {
      id: number;
      title: string;
      slug: string | null;
    } | null;
  };

  let { data } = $props();

  const levelLabel = (value: string) => {
    switch (value) {
      case "success":
        return "Success";
      case "warning":
        return "Warning";
      case "error":
        return "Error";
      default:
        return "Info";
    }
  };

  const levelVariant = (value: string) => {
    switch (value) {
      case "success":
        return "default";
      case "warning":
        return "secondary";
      case "error":
        return "destructive";
      default:
        return "outline";
    }
  };

  const formatDate = (value: string) => {
    if (!value) {
      return "Unknown time";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    return new Intl.DateTimeFormat("ru-RU", {
      dateStyle: "medium",
      timeStyle: "medium"
    }).format(date);
  };
</script>

<div class="flex w-full flex-col gap-4 px-4 py-6 md:px-6">
  <Card>
    <CardHeader>
      <CardTitle>События связок</CardTitle>
      <CardDescription>
        Лог автоматической цепочки `Kinozal -> TMDB -> Vault` после успешного сохранения torrent-файла.
      </CardDescription>
    </CardHeader>
    <CardContent class="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
      <span>Событий: {data.events.length}</span>
      {#if data.apiError}
        <Badge variant="destructive">{data.apiError}</Badge>
      {/if}
    </CardContent>
  </Card>

  {#if data.events.length === 0}
    <Card>
      <CardContent class="py-8 text-sm text-muted-foreground">
        История пока пуста.
      </CardContent>
    </Card>
  {:else}
    <div class="grid gap-3">
      {#each data.events as event (event.id)}
        <Card>
          <CardHeader class="gap-3">
            <div class="flex flex-wrap items-center gap-2">
              <Badge variant={levelVariant(event.level)}>{levelLabel(event.level)}</Badge>
              <Badge variant="outline">{event.event_type}</Badge>
              <span class="text-sm text-muted-foreground">{formatDate(event.created_at)}</span>
            </div>
            <CardTitle class="text-base">{event.message}</CardTitle>
            <CardDescription>
              operation: {event.operation_id}
            </CardDescription>
          </CardHeader>
          <CardContent class="grid gap-2 text-sm">
            <div class="flex flex-wrap gap-x-4 gap-y-2">
              <span><strong>Source:</strong> {event.source}</span>
              {#if event.movie_rss_title}
                <span><strong>RSS:</strong> {event.movie_rss_title}</span>
              {/if}
              {#if event.rss_kinozal_id}
                <span><strong>RSS Kinozal ID:</strong> {event.rss_kinozal_id}</span>
              {/if}
              {#if event.torrent_kinozal_id}
                <span><strong>Torrent ID:</strong> {event.torrent_kinozal_id}</span>
              {/if}
              {#if event.imdb_id}
                <span><strong>IMDb:</strong> {event.imdb_id}</span>
              {/if}
              {#if event.kinopoisk_id}
                <span><strong>KP:</strong> {event.kinopoisk_id}</span>
              {/if}
              {#if event.tmdb_id}
                <span><strong>TMDB:</strong> {event.tmdb_id}</span>
              {/if}
            </div>

            {#if event.vault_movie}
              <div class="text-sm">
                <strong>Vault:</strong>
                {#if event.vault_movie.slug}
                  <a class="underline underline-offset-4" href={`/movies/${event.vault_movie.slug}`}>
                    {event.vault_movie.title}
                  </a>
                {:else}
                  <span>{event.vault_movie.title}</span>
                {/if}
              </div>
            {/if}
          </CardContent>
        </Card>
      {/each}
    </div>
  {/if}
</div>
