export type BestfilmsofGenre = {
  slug: string;
  label: string;
};

export type BestfilmsofPreset = {
  name: string;
  weights: Record<string, number> | null;
};

export type BestfilmsofFilters = {
  years: number[];
  genres: BestfilmsofGenre[];
  presets: BestfilmsofPreset[];
  weight_keys: string[];
  year_min: number;
  year_max: number;
};

export type BestfilmsofMovie = {
  position: number;
  score: number | null;
  imdb_id: string;
  tmdb_id: number;
  title: string;
  title_ru: string | null;
  overview: string | null;
  overview_ru: string | null;
  poster_path: string | null;
  release_date: string | null;
  imdb_rating: number | null;
  imdb_votes: number | null;
  tomato_meter: number | null;
  metascore: number | null;
  gross: number | null;
  gross_scope: string | null;
  oscar_wins: number;
  oscar_nominations: number;
  best_picture: boolean;
  award_points: number;
  awards_wins: number | null;
  awards_nominations: number | null;
  other_awards: unknown[];
  in_collection: boolean;
  collection_slug: string | null;
  watch_status: "watched" | "will_watch" | "wont_watch" | null;
  in_favorites: boolean;
  rating: number | null;
};

export type BestfilmsofStatusFilter = "all" | "unwatched" | "will_watch";

export type BestfilmsofMovieList = {
  mode: "list";
  year: number;
  genre: string;
  total: number;
  page: number;
  limit: number;
  movies: BestfilmsofMovie[];
  weights: Record<string, number> | null;
  preset: string;
  status_filter: BestfilmsofStatusFilter;
  counts: Record<BestfilmsofStatusFilter, number>;
  state: "idle" | "queued" | "syncing" | "ready" | "error";
  synced_at: string | null;
  is_stale: boolean;
  error: string | null;
};

export type BestfilmsofGenreYear = {
  year: number;
  count: number;
  top_score: number | null;
  top_imdb_id: string;
  top_tmdb_id: number;
  top_title: string;
  top_title_ru: string | null;
  top_overview_ru: string | null;
  top_poster_path: string | null;
  top_release_date: string | null;
  in_collection: boolean;
  collection_slug: string | null;
  watch_status: "watched" | "will_watch" | "wont_watch" | null;
  in_favorites: boolean;
  rating: number | null;
};

export type BestfilmsofGenreSummary = {
  mode: "summary";
  genre: string;
  total: number;
  years: BestfilmsofGenreYear[];
  state: "idle" | "queued" | "syncing" | "ready" | "error";
  synced_at: string | null;
  is_stale: boolean;
  error: string | null;
};

export type BestfilmsofSyncState = {
  key: string;
  state: "idle" | "queued" | "syncing" | "ready" | "error";
  synced_at: string | null;
  started_at: string | null;
  worker_started_at: string | null;
  finished_at: string | null;
  error: string | null;
  stats: Record<string, unknown> | null;
};

export const PRESET_LABELS: Record<string, string> = {
  default: "По умолчанию (сайт)",
  critics: "Критики",
  crowd: "Зрители",
  awards: "Награды",
  "no-boxoffice": "Без кассы",
  custom: "Свои веса"
};

export const WEIGHT_LABELS: Record<string, string> = {
  imdb: "IMDb",
  critics: "Критики",
  awards: "Награды",
  boxoffice: "Касса"
};
