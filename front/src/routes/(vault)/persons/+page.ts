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

const ALLOWED_ORDERS = new Set([
  "name",
  "-name",
  "original_name",
  "-original_name",
  "birth_date",
  "-birth_date",
]);

export const load: PageLoad = async ({ fetch, url }) => {
  const q = (url.searchParams.get("q") ?? "").trim();
  const isFavorite = url.searchParams.get("is_favorite") === "true";
  const isStar = url.searchParams.get("is_star") === "true";
  const lang = url.searchParams.get("lang") === "en" ? "en" : "ru";

  let order = (url.searchParams.get("order") ?? "").trim();
  if (!ALLOWED_ORDERS.has(order)) {
    order = lang === "en" ? "original_name" : "name";
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
        persons: [] as ApiPerson[],
        apiError: `API error: ${response.status}`,
        activeQuery: q,
        activeIsFavorite: isFavorite,
        activeIsStar: isStar,
        activeOrder: order,
        activeLang: lang,
      };
    }
    const persons = (await response.json()) as ApiPerson[];
    return {
      persons,
      apiError: "",
      activeQuery: q,
      activeIsFavorite: isFavorite,
      activeIsStar: isStar,
      activeOrder: order,
      activeLang: lang,
    };
  } catch (err) {
    return {
      persons: [] as ApiPerson[],
      apiError: err instanceof Error ? err.message : "Unknown API error",
      activeQuery: q,
      activeIsFavorite: isFavorite,
      activeIsStar: isStar,
      activeOrder: order,
      activeLang: lang,
    };
  }
};
