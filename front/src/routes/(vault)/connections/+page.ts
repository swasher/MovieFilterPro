import type { PageLoad } from "./$types";

type ApiConnectionEvent = {
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

type ApiConnectionEventsResponse = {
  items?: ApiConnectionEvent[];
};

export const load: PageLoad = async ({ fetch }) => {
  try {
    const response = await fetch("/api/vault/connection-events?limit=100");
    if (!response.ok) {
      return {
        events: [] as ApiConnectionEvent[],
        apiError: `API error: ${response.status}`
      };
    }

    const payload = (await response.json()) as ApiConnectionEventsResponse;
    return {
      events: payload.items ?? [],
      apiError: ""
    };
  } catch (error) {
    return {
      events: [] as ApiConnectionEvent[],
      apiError: error instanceof Error ? error.message : "Unknown API error"
    };
  }
};
