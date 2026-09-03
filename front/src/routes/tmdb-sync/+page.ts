import type { PageLoad } from "./$types";

type QueueItem = {
  id: number;
  movie_id: number;
  movie_slug: string;
  movie_title: string;
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
};

export const load: PageLoad = async ({ fetch }) => {
  const [stateResponse, itemsResponse] = await Promise.all([
    fetch("/api/vault/tmdb-sync/state"),
    fetch("/api/vault/tmdb-sync/items?limit=100"),
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
    apiError: !stateResponse.ok ? stateResponse.status : 0,
  };
};