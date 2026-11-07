import type { PageLoad } from "./$types";

type ApiPerson = {
  id: number;
  name: string;
  original_name: string | null;
  photo_url: string | null;
  birth_date: string | null;
  death_date: string | null;
  movies_count: number;
  is_favorite: boolean;
  is_star: boolean;
};

type ApiHomePersonGroup = {
  id: string;
  title: string;
  see_all_href: string;
  persons: ApiPerson[];
};

const ALLOWED_ORDERS = new Set([
  "name",
  "-name",
  "original_name",
  "-original_name",
  "birth_date",
  "-birth_date",
  "updated_at",
  "-updated_at",
  "popularity",
  "-popularity",
  "movies_count",
  "-movies_count",
]);

export const load: PageLoad = async ({ fetch, url }) => {
  const q = (url.searchParams.get("q") ?? "").trim();
  const isFavorite = url.searchParams.get("is_favorite") === "true";
  const isStar = url.searchParams.get("is_star") === "true";
  const lang = url.searchParams.get("lang") === "en" ? "en" : "ru";

  // Как на главной фильмов: без query params показываем подборки, с любым
  // параметром — обычный список персон.
  const isHome = ![...url.searchParams.keys()].length;

  let order = (url.searchParams.get("order") ?? "").trim();
  if (!ALLOWED_ORDERS.has(order)) {
    order = lang === "en" ? "original_name" : "name";
  }

  const baseState = {
    persons: [] as ApiPerson[],
    homeGroups: [] as ApiHomePersonGroup[],
    apiError: "",
    activeQuery: q,
    activeIsFavorite: isFavorite,
    activeIsStar: isStar,
    activeOrder: order,
    activeLang: lang,
    isHome,
  };

  if (isHome) {
    try {
      const response = await fetch("/api/vault/persons/home");
      const payload = response.ok
        ? ((await response.json()) as { groups?: ApiHomePersonGroup[] })
        : { groups: [] as ApiHomePersonGroup[] };

      return {
        ...baseState,
        homeGroups: payload.groups ?? [],
        apiError: !response.ok ? `API error: ${response.status}` : "",
      };
    } catch (err) {
      return {
        ...baseState,
        apiError: err instanceof Error ? err.message : "Unknown API error",
      };
    }
  }

  const params = new URLSearchParams({ limit: "50" });
  if (q) params.set("q", q);
  if (isFavorite) params.set("is_favorite", "true");
  if (isStar) params.set("is_star", "true");
  params.set("order", order);

  try {
    const response = await fetch(`/api/vault/persons?${params.toString()}`);
    if (!response.ok) {
      return {
        ...baseState,
        apiError: `API error: ${response.status}`,
      };
    }
    const persons = (await response.json()) as ApiPerson[];
    return {
      ...baseState,
      persons,
    };
  } catch (err) {
    return {
      ...baseState,
      apiError: err instanceof Error ? err.message : "Unknown API error",
    };
  }
};
