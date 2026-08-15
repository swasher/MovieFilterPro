import type { PageLoad } from "./$types";

type ApiMovie = {
  id: number;
  title: string;
  original_title: string | null;
  year: number | null;
  slug: string;
  poster_url: string | null;
  movie_type: string | null;
  in_watched: boolean;
  in_wont_watch: boolean;
  in_favorites: boolean;
};

type ApiGenre = {
  name: string;
  slug: string;
};

export const load: PageLoad = async ({ fetch, url }) => {
  const genre = url.searchParams.getAll("genre");
  const yearFrom = url.searchParams.get("year_from") ?? "";
  const yearTo = url.searchParams.get("year_to") ?? "";
  const movieType = url.searchParams.get("movie_type") ?? "";
  const watchStatus = url.searchParams.get("watch_status") ?? "";
  const isFavorite = url.searchParams.get("is_favorite") === "true";
  const status = (url.searchParams.get("status") ?? "").trim();
  const list = (url.searchParams.get("list") ?? "").trim();
  const q = (url.searchParams.get("q") ?? "").trim();
  const order = (url.searchParams.get("order") ?? "-year").trim();
  const offset = parseInt(url.searchParams.get("offset") ?? "0", 10);

  try {
    const params = new URLSearchParams({ limit: "30", offset: offset.toString() });
    if (genre.length > 0) params.set("genre", genre.join(","));
    if (yearFrom) params.set("year_from", yearFrom);
    if (yearTo) params.set("year_to", yearTo);
    if (movieType) params.set("movie_type", movieType);
    if (watchStatus) params.set("watch_status", watchStatus);
    if (isFavorite) params.set("is_favorite", "true");
    if (status) params.set("status", status);
    if (list) params.set("list", list);
    if (q) params.set("q", q);
    if (order && order !== "-year") params.set("order", order);

    const [moviesResponse, genresResponse] = await Promise.all([
      fetch(`/api/vault/movies?${params.toString()}`),
      fetch("/api/vault/genres"),
    ]);

    const movies = moviesResponse.ok
      ? ((await moviesResponse.json()) as ApiMovie[])
      : [];
    const genres = genresResponse.ok
      ? ((await genresResponse.json()) as ApiGenre[])
      : [];

    return {
      movies,
      genres,
      apiError: !moviesResponse.ok ? `API error: ${moviesResponse.status}` : "",
      activeGenre: genre,
      activeYearFrom: yearFrom,
      activeYearTo: yearTo,
      activeMovieType: movieType,
      activeWatchStatus: watchStatus,
      activeIsFavorite: isFavorite,
      activeStatus: status,
      activeList: list,
      activeQuery: q,
      activeOrder: order,
      initialOffset: offset,
    };
  } catch (error) {
    return {
      movies: [] as ApiMovie[],
      genres: [] as ApiGenre[],
      apiError: error instanceof Error ? error.message : "Unknown API error",
      activeGenre: genre,
      activeYearFrom: yearFrom,
      activeYearTo: yearTo,
      activeMovieType: movieType,
      activeWatchStatus: watchStatus,
      activeIsFavorite: isFavorite,
      activeStatus: status,
      activeList: list,
      activeQuery: q,
      activeOrder: order,
      initialOffset: offset,
    };
  }
};
