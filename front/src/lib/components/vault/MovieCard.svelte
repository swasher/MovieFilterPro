<script lang="ts">
  import { Card, CardContent } from "$lib/components/ui/card";
  import { Badge } from "$lib/components/ui/badge";
  import { Link2, Link2Off } from "@lucide/svelte";
  import { QBT_DOWNLOADING_STATES } from "$lib/qbittorrent";
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
    torrent_linked: boolean;
    torrent_info_hash: string | null;
  };

  let {
    movie,
    activeStatus = null,
    torrentProgress = null,
    torrentState = null
  }: {
    movie: MovieCardData;
    activeStatus?: string | null;
    torrentProgress?: number | null;
    torrentState?: string | null;
  } = $props();

  const showTorrentStatus = $derived(
    activeStatus === "will_watch" || movie.watch_status === "will_watch"
  );

  const isDownloading = $derived(
    Boolean(
      torrentState &&
        QBT_DOWNLOADING_STATES.has(torrentState) &&
        torrentProgress !== null &&
        torrentProgress < 1
    )
  );

  const progressPercent = $derived(
    torrentProgress === null
      ? null
      : Math.floor(Math.min(1, Math.max(0, torrentProgress)) * 100)
  );

  const torrentTitle = $derived(
    movie.torrent_linked
      ? `Раздача привязана${movie.torrent_info_hash ? ` · ${movie.torrent_info_hash.slice(0, 8)}…` : ""}`
      : "Раздача не привязана"
  );
</script>

<Card class="relative h-[270px] w-[180px] flex-none overflow-hidden rounded-md border !gap-0 !py-0 transition hover:shadow-md">
  <CardContent class="h-full !p-0">
    <MovieStatusBadges
      watch_status={movie.watch_status}
      rating={movie.rating}
      is_favorite={movie.in_favorites && activeStatus !== "favorites"}
      year={movie.year}
    />

    {#if showTorrentStatus}
      <div class="absolute top-1.5 left-1.5 z-10 flex flex-col items-start gap-1">
        <span
          class={`flex size-5 items-center justify-center rounded-full text-white shadow-md ${
            movie.torrent_linked ? "bg-emerald-500" : "bg-zinc-600/85"
          }`}
          title={torrentTitle}
          aria-label={torrentTitle}
        >
          {#if movie.torrent_linked}
            <Link2 class="size-3" />
          {:else}
            <Link2Off class="size-3" />
          {/if}
        </span>
        {#if isDownloading && progressPercent !== null}
          <span class="rounded-full bg-black/70 px-1.5 py-0.5 text-[10px] font-medium leading-none text-white shadow-md">
            {progressPercent}%
          </span>
        {/if}
      </div>
    {/if}

    {#if movie.movie_type === "series" || movie.movie_type === "miniseries"}
      <Badge variant="secondary" class="absolute bottom-1.5 left-1.5 z-10 px-1.5 py-0.5 text-[10px]">{movie.movie_type === "miniseries" ? "MINISERIES" : "SERIES"}</Badge>
    {/if}

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
