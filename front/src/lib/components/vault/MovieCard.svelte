<script lang="ts">
  import { Card, CardContent } from "$lib/components/ui/card";
  import { Badge } from "$lib/components/ui/badge";
  import MovieStatusBadges from "./MovieStatusBadges.svelte";

  type MovieCardData = {
    id: number;
    title: string;
    slug: string;
    poster_url: string | null;
    movie_type: string | null;
    year: number | null;
    watch_status: "watched" | "will_watch" | "wont_watch" | null;
    rating: number | null;
    in_favorites: boolean;
  };

  let {
    movie,
    activeStatus = null
  }: {
    movie: MovieCardData;
    activeStatus?: string | null;
  } = $props();
</script>

<Card class="relative h-[270px] w-[180px] flex-none overflow-hidden rounded-md border !gap-0 !py-0 transition hover:shadow-md">
  <CardContent class="h-full !p-0">
    <MovieStatusBadges
      watch_status={activeStatus === movie.watch_status ? null : movie.watch_status}
      rating={movie.rating}
      is_favorite={movie.in_favorites && activeStatus !== "favorites"}
      position="top-left"
    />

    {#if movie.movie_type === "series" || movie.movie_type === "miniseries"}
      <Badge variant="secondary" class="absolute bottom-2 left-2 z-10 px-1.5 py-0.5 text-[10px]">{movie.movie_type === "miniseries" ? "MINISERIES" : "SERIES"}</Badge>
    {/if}

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