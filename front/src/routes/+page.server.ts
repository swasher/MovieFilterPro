import type { PageServerLoad } from "./$types";
import { env } from "$env/dynamic/private";

type ApiMovie = {
  id: number;
  title: string;
  original_title: string | null;
  year: number | null;
  slug: string;
};

const API_BASE_URL = env.API_BASE_URL ?? "http://127.0.0.1:8000";

export const load: PageServerLoad = async ({ fetch }) => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/vault/movies?limit=30`);
    if (!response.ok) {
      return {
        movies: [] as ApiMovie[],
        apiError: `API error: ${response.status}`
      };
    }

    const movies = (await response.json()) as ApiMovie[];
    return {
      movies,
      apiError: ""
    };
  } catch (error) {
    return {
      movies: [] as ApiMovie[],
      apiError: error instanceof Error ? error.message : "Unknown API error"
    };
  }
};
