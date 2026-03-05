import type { PageServerLoad } from "./$types";
import { env } from "$env/dynamic/private";

type ApiMovie = {
  id: number;
  title: string;
  original_title: string | null;
  year: number | null;
  slug: string;
  poster_url: string | null;
};

const API_BASE_URL = env.API_BASE_URL ?? "http://127.0.0.1:8000";

export const load: PageServerLoad = async ({ fetch, url }) => {
  const genre = (url.searchParams.get("genre") ?? "").trim();
  const status = (url.searchParams.get("status") ?? "").trim();
  const list = (url.searchParams.get("list") ?? "").trim();
  try {
    const params = new URLSearchParams({ limit: "30" });
    const selectedGenre = genre;
    if (selectedGenre) {
      params.set("genre", selectedGenre);
    }
    if (status) {
      params.set("status", status);
    }
    if (list) {
      params.set("list", list);
    }

    const response = await fetch(`${API_BASE_URL}/api/vault/movies?${params.toString()}`);
    if (!response.ok) {
      return {
        movies: [] as ApiMovie[],
        apiError: `API error: ${response.status}`,
        activeGenre: selectedGenre,
        activeStatus: status,
        activeList: list
      };
    }

    const movies = (await response.json()) as ApiMovie[];
    return {
      movies,
      apiError: "",
      activeGenre: selectedGenre,
      activeStatus: status,
      activeList: list
    };
  } catch (error) {
    return {
      movies: [] as ApiMovie[],
      apiError: error instanceof Error ? error.message : "Unknown API error",
      activeGenre: genre,
      activeStatus: status,
      activeList: list
    };
  }
};
