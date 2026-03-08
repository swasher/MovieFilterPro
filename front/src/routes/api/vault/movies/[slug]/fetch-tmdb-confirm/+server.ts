import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { djangoFetch } from "$lib/server/django";

export const POST: RequestHandler = async (event) => {
  const { params, request } = event;
  const payload = await request.json();

  const response = await djangoFetch(event, `/api/vault/movies/${params.slug}/fetch-tmdb-confirm`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  const data = await response.json();
  return json(data, { status: response.status });
};
