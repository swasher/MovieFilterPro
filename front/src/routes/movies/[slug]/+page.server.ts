import { env } from "$env/dynamic/private";
import { error } from "@sveltejs/kit";
import type { PageServerLoad } from "./$types";

type ApiMovieDetail = {
  id: number;
  title: string;
  original_title: string | null;
  year: number | null;
  slug: string;
  description: string;
  movie_type: string;
  status: string;
  imdb_rating: number | null;
  poster_url: string | null;
};

const API_BASE_URL = env.API_BASE_URL ?? "http://127.0.0.1:8000";

export const load: PageServerLoad = async ({ fetch, params }) => {
  const response = await fetch(`${API_BASE_URL}/api/vault/movies/${params.slug}`);
  if (response.status === 404) {
    throw error(404, "Movie not found");
  }
  if (!response.ok) {
    throw error(response.status, `API error: ${response.status}`);
  }

  const movie = (await response.json()) as ApiMovieDetail;
  return { movie };
};
