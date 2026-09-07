import type { PageLoad } from "./$types";

type QueueItem = {
  id: number;
  movie_id: number;
  movie_slug: string;
  movie_title: string;
  movie_original_title: string;
  movie_year: number | null;
  movie_description: string;
  movie_poster_url: string | null;
  movie_has_tmdb: boolean;
  snapshot_title: string;
  snapshot_original_title: string;
  snapshot_year: number | null;
  state: string;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  result_status: string;
  result_title: string;
  result_original_title: string;
  result_year: number | null;
  result_tmdb_id: number | null;
  result_media_type: string;
  result_message: string;
  retry_count: number;
};

type QueueStateResp = {
  enabled: boolean;
  counters: Record<string, number>;
  total_unsynced: number;
  missing_keys?: string[];
};

const PAGE_SIZE = 100;

export const load: PageLoad = async ({ fetch, url }) => {
  const rawPage = Number(url.searchParams.get("page") ?? "1");
  const page = Number.isFinite(rawPage) ? Math.max(1, Math.floor(rawPage)) : 1;
  const offset = (page - 1) * PAGE_SIZE;

  const [stateResponse, itemsResponse] = await Promise.all([
    fetch("/api/vault/tmdb-sync/state"),
    fetch(`/api/vault/tmdb-sync/items?limit=${PAGE_SIZE}&offset=${offset}`),
  ]);

  const state = stateResponse.ok
    ? ((await stateResponse.json()) as QueueStateResp)
    : null;
  const itemsPayload = itemsResponse.ok
    ? ((await itemsResponse.json()) as { items: QueueItem[]; total: number })
    : null;

  return {
    state,
    items: itemsPayload?.items ?? [],
    total: itemsPayload?.total ?? 0,
    page,
    apiError: !stateResponse.ok ? stateResponse.status : 0,
  };
};