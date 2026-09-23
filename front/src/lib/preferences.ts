export type PreferencesData = {
  last_scan: string | null;
  scan_from_page: number | null;
  countries: string;
  genres: string;
  max_year: number;
  min_rating: number;
  low_countries: string;
  low_genres: string;
  low_max_year: number;
  low_min_rating: number;
  plex_address: string | null;
  plex_token: string | null;
  cookie_pass: string | null;
  cookie_uid: string | null;
  kinozal_domain: string | null;
  torrents_hotfolder: string | null;
  resolved_torrents_hotfolder: string | null;
  hotfolder_exists: boolean;
  hotfolder_hint: string;
  ignore_title: string;
  tmdb_api_key: string | null;
  omdb_api_key: string | null;
  tmdb_v4_read_access_token: string | null;
  tmdb_v4_authenticated_access_token: string | null;
  ai_enabled: boolean;
  ai_base_url: string | null;
  ai_api_key: string | null;
  ai_model: string | null;
  groq_api_key: string | null;
  groq_model: string | null;
};

export type PreferencesUpdatePayload = {
  last_scan: string | null;
  scan_from_page: number | null;
  countries: string;
  genres: string;
  max_year: number;
  min_rating: number;
  low_countries: string;
  low_genres: string;
  low_max_year: number;
  low_min_rating: number;
  plex_address: string | null;
  plex_token: string | null;
  cookie_pass: string | null;
  cookie_uid: string | null;
  kinozal_domain: string | null;
  torrents_hotfolder: string | null;
  ignore_title: string;
  tmdb_api_key: string | null;
  omdb_api_key: string | null;
  tmdb_v4_read_access_token: string | null;
  ai_enabled: boolean;
  ai_base_url: string | null;
  ai_api_key: string | null;
  ai_model: string | null;
  groq_api_key: string | null;
  groq_model: string | null;
};

export type PreferencesApiErrorPayload = {
  detail?: string;
};

export const emptyPreferences = (): PreferencesData => ({
  last_scan: null,
  scan_from_page: 0,
  countries: "",
  genres: "",
  max_year: 1990,
  min_rating: 3,
  low_countries: "",
  low_genres: "",
  low_max_year: 2000,
  low_min_rating: 5,
  plex_address: null,
  plex_token: null,
  cookie_pass: null,
  cookie_uid: null,
  kinozal_domain: null,
  torrents_hotfolder: null,
  resolved_torrents_hotfolder: null,
  hotfolder_exists: false,
  hotfolder_hint: "",
  ignore_title: "",
  tmdb_api_key: null,
  omdb_api_key: null,
  tmdb_v4_read_access_token: null,
  tmdb_v4_authenticated_access_token: null,
  ai_enabled: false,
  ai_base_url: null,
  ai_api_key: null,
  ai_model: null,
  groq_api_key: null,
  groq_model: null
});
