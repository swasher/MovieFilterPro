import { error } from "@sveltejs/kit";
import type { PageLoad } from "./$types";

type ApiMovieDetail = {
  id: number;
  title: string;
  original_title: string | null;
  year: number | null;
  slug: string;
  description: string;
  movie_type: string;
  movie_type_display: string;
  status: string;
  status_display: string;
  imdb_rating: number | null;
  imdb_id: string | null;
  kinopoisk_id: number | null;
  tvdb_id: number | null;
  homepage: string | null;
  poster_url: string | null;
  duration: number | null;
  age_rating: string | null;
  trailer_url: string | null;
  tmdb_id: number | null;
  tmdb_linked: boolean;
  tmdb_media_type: string | null;
  tmdb_vote_average: number | null;
  tmdb_vote_count: number | null;
  tmdb_original_language: string | null;
  omdb_imdb_rating: number | null;
  omdb_imdb_votes: number | null;
  omdb_rotten_tomatoes: number | null;
  omdb_metacritic: number | null;
  omdb_last_synced_at: string | null;
  budget: number | null;
  source: string;
  source_display: string;
  genres: Array<{ name: string; slug: string | null }>;
  countries: Array<{ name: string; slug?: string | null }>;
  keywords: string[];
  user_state: {
    in_watched: boolean;
    in_will_watch: boolean;
    in_wont_watch: boolean;
    in_favorites: boolean;
    rating: number | null;
    rated_at: string | null;
    status_at: string | null;
    watched_at: string | null;
    note: string;
    note_at: string | null;
    favorited_at: string | null;
  };
  custom_lists: Array<{
    id: number;
    name: string;
    is_public: boolean;
    is_in_list: boolean;
  }>;
  directors: Array<{
    id: number;
    name: string;
    photo_url: string | null;
    character_name?: string | null;
    is_favorite?: boolean;
    popularity?: number | null;
  }>;
  producers: Array<{
    id: number;
    name: string;
    photo_url: string | null;
    character_name?: string | null;
    is_favorite?: boolean;
    popularity?: number | null;
  }>;
  screenplays: Array<{
    id: number;
    name: string;
    photo_url: string | null;
    character_name?: string | null;
    is_favorite?: boolean;
    popularity?: number | null;
  }>;
  writers: Array<{
    id: number;
    name: string;
    photo_url: string | null;
    character_name?: string | null;
    is_favorite?: boolean;
    popularity?: number | null;
  }>;
  showrunners: Array<{
    id: number;
    name: string;
    photo_url: string | null;
    character_name?: string | null;
    is_favorite?: boolean;
    popularity?: number | null;
  }>;
  actors: Array<{
    id: number;
    name: string;
    photo_url: string | null;
    character_name?: string | null;
    is_favorite?: boolean;
    popularity?: number | null;
  }>;
  seasons: Array<{
    id: number;
    season_number: number;
    title: string;
    description: string;
    release_date: string | null;
    poster_url: string | null;
    episodes_count: number;
    air_year: number | null;
    user_state: {
      watch_status: "watched" | "plan" | "skip" | null;
      rating: number | null;
    };
  }>;
  collection: {
    tmdb_id: number;
    name: string;
    overview: string | null;
    poster_url: string | null;
    backdrop_url: string | null;
    parts: Array<{
      tmdb_id: number;
      title: string;
      original_title: string | null;
      year: number | null;
      poster_url: string | null;
      in_vault: boolean;
      vault_slug: string | null;
    }>;
  } | null;
  writeback?: {
    status: string;
    last_error: string | null;
    next_retry_at: string | null;
    reason: string | null;
  } | null;
};

export const load: PageLoad = async ({ fetch, params }) => {
  const response = await fetch(`/api/vault/movies/${params.slug}`);
  if (response.status === 404) {
    throw error(404, "Movie not found");
  }
  if (!response.ok) {
    throw error(response.status, `API error: ${response.status}`);
  }

  const movie = (await response.json()) as ApiMovieDetail;
  return { movie };
};
