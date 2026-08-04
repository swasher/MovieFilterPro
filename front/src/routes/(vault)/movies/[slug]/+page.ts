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
  poster_url: string | null;
  duration: number | null;
  age_rating: string | null;
  trailer_url: string | null;
  tmdb_id: number | null;
  tmdb_linked: boolean;
  tmdb_media_type: string | null;
  source: string;
  source_display: string;
  genres: Array<{ name: string; slug: string | null }>;
  countries: Array<{ name: string; slug?: string | null }>;
  user_state: {
    in_watched: boolean;
    in_will_watch: boolean;
    in_wont_watch: boolean;
    in_favorites: boolean;
    rating: number | null;
    note: string;
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
  }>;
  actors: Array<{
    id: number;
    name: string;
    photo_url: string | null;
    character_name?: string | null;
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
