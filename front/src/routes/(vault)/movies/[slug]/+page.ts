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
  }>;
  actors: Array<{
    id: number;
    name: string;
    photo_url: string | null;
    character_name?: string | null;
    is_favorite?: boolean;
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
