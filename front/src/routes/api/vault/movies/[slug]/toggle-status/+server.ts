import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { djangoFetch } from "$lib/server/django";

export const POST: RequestHandler = async (event) => {
  const { params, request } = event;
  const body = (await request.json()) as { status_key: string };
  const response = await djangoFetch(event, `/api/vault/movies/${params.slug}/toggle-status`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  });

  const payload = await response.json();
  return json(payload, { status: response.status });
};
