export const KINOZAL_PAGE_SIZE = 20;
export const DEFAULT_PRIORITY_FILTER = "HIGH";
export const DEFAULT_SORT_KEY = "date_added";
export const DEFAULT_REVERSE = false;

export type KinozalPriorityFilter =
  | "ALL"
  | "HIGH"
  | "LOW"
  | "DEFER"
  | "SKIP"
  | "WAIT_TRANS"
  | "TRANS_FOUND";

export type KinozalSortKey =
  | "date_added"
  | "title"
  | "year"
  | "imdb_rating"
  | "kinopoisk_rating";

export type KinozalMovie = {
  id: number;
  kinozal_id: number;
  title: string;
  original_title: string | null;
  year: string;
  date_added: string;
  plot: string;
  translate: string | null;
  poster_url: string | null;
  imdb_id?: string | null;
  imdb_rating: number | null;
  kinopoisk_id?: number | null;
  kinopoisk_rating: number | null;
  priority_key: string;
  priority_label: string;
  kinorium_partial_match: boolean;
  genres: string[];
  countries: string[];
  directors: string[];
  actors: string[];
  open_url: string | null;
  kinorium_url?: string | null;
};

export type KinozalMoviesPage = {
  items: KinozalMovie[];
  next_cursor: string | null;
  has_more: boolean;
  limit: number;
  total_count: number;
};

export type KinozalSummary = {
  last_scan: string | null;
  total: number;
  high: number;
  low: number;
  defer: number;
  skip: number;
  wait_trans: number;
  trans_found: number;
};

export type KinozalActionResponse = {
  id: number;
  title: string;
  previous_priority_key: string;
  current_priority_key: string;
  message: string;
};

export type KinozalDownloadOption = {
  id: number;
  header: string;
  size: string;
  seed: string;
  peer: string;
  created: string;
  link: string;
  is_4k: boolean;
  is_sdr: boolean;
};

export type KinozalDownloadOptionsResponse = {
  movie_id: number;
  title: string;
  items: KinozalDownloadOption[];
};

export type KinozalTorrentDownloadResponse = {
  torrent_id: number;
  message: string;
  filename: string | null;
  saved_to: string | null;
  operation_id?: string | null;
};

export type KinozalApiErrorDetail = {
  code?: string;
  message?: string;
  hint?: string;
};

export type KinozalApiErrorPayload = {
  detail?: string | KinozalApiErrorDetail;
};

export const emptyKinozalMoviesPage = (): KinozalMoviesPage => ({
  items: [],
  next_cursor: null,
  has_more: false,
  limit: KINOZAL_PAGE_SIZE,
  total_count: 0
});

export const emptyKinozalSummary = (): KinozalSummary => ({
  last_scan: null,
  total: 0,
  high: 0,
  low: 0,
  defer: 0,
  skip: 0,
  wait_trans: 0,
  trans_found: 0
});

export const KINOZAL_PRIORITY_OPTIONS: Array<{
  value: KinozalPriorityFilter;
  label: string;
}> = [
  { value: "HIGH", label: "High" },
  { value: "LOW", label: "Low" },
  { value: "DEFER", label: "Defer" },
  { value: "WAIT_TRANS", label: "Wait trans" },
  { value: "TRANS_FOUND", label: "Trans found" },
  { value: "SKIP", label: "Skip" }
];

export const KINOZAL_SORT_OPTIONS: Array<{
  value: KinozalSortKey;
  label: string;
}> = [
  { value: "date_added", label: "По дате скана" },
  { value: "title", label: "По названию" },
  { value: "year", label: "По году" },
  { value: "imdb_rating", label: "Рейтинг IMDB" },
  { value: "kinopoisk_rating", label: "Рейтинг KP" }
];
