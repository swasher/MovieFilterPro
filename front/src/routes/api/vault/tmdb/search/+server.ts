import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { djangoFetch } from "$lib/server/django";

export const GET: RequestHandler = async (event) => {
  const q = (event.url.searchParams.get("q") ?? "").trim();
  const limit = (event.url.searchParams.get("limit") ?? "10").trim();
  const params = new URLSearchParams();

  if (q) {
    params.set("q", q);
  }
  if (limit) {
    params.set("limit", limit);
  }

  const suffix = params.toString();
  const response = await djangoFetch(event, suffix ? `/api/vault/tmdb/search?${suffix}` : "/api/vault/tmdb/search");
  const payload = await response.json();
  return json(payload, { status: response.status });
};
