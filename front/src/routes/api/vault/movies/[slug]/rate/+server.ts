import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { djangoFetch } from "$lib/server/django";

export const POST: RequestHandler = async (event) => {
  const { params, request } = event;
  const body = (await request.json()) as { rating: number | null };
  const response = await djangoFetch(event, `/api/vault/movies/${params.slug}/rate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  });

  const payload = await response.json();
  return json(payload, { status: response.status });
};
