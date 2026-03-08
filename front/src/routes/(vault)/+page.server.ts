import type { PageServerLoad } from "./$types";
import { djangoFetch } from "$lib/server/django";

type ApiMovie = {
  id: number;
  title: string;
  original_title: string | null;
  year: number | null;
  slug: string;
  poster_url: string | null;
};

export const load: PageServerLoad = async (event) => {
  const { url } = event;
  const genre = (url.searchParams.get("genre") ?? "").trim();
  const status = (url.searchParams.get("status") ?? "").trim();
  const list = (url.searchParams.get("list") ?? "").trim();
  const q = (url.searchParams.get("q") ?? "").trim();
  const order = (url.searchParams.get("order") ?? "-year").trim();
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
    if (q) {
      params.set("q", q);
    }
    if (order && order !== "-year") {
      params.set("order", order);
    }

    const response = await djangoFetch(event, `/api/vault/movies?${params.toString()}`);
    if (!response.ok) {
      return {
        movies: [] as ApiMovie[],
        apiError: `API error: ${response.status}`,
        activeGenre: selectedGenre,
        activeStatus: status,
        activeList: list,
        activeQuery: q,
        activeOrder: order
      };
    }

    const movies = (await response.json()) as ApiMovie[];
    return {
      movies,
      apiError: "",
      activeGenre: selectedGenre,
      activeStatus: status,
      activeList: list,
      activeQuery: q,
      activeOrder: order
    };
  } catch (error) {
    return {
      movies: [] as ApiMovie[],
      apiError: error instanceof Error ? error.message : "Unknown API error",
      activeGenre: genre,
      activeStatus: status,
      activeList: list,
      activeQuery: q,
      activeOrder: order
    };
  }
};
