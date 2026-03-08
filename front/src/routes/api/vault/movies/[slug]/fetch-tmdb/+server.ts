import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { djangoFetch } from "$lib/server/django";

export const POST: RequestHandler = async (event) => {
  const { params, request } = event;
  let forceRematch = false;
  try {
    const body = (await request.json()) as { force_rematch?: boolean };
    forceRematch = Boolean(body.force_rematch);
  } catch {
    forceRematch = false;
  }

  const response = await djangoFetch(event, `/api/vault/movies/${params.slug}/fetch-tmdb`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      force_rematch: forceRematch
    })
  });

  const payload = await response.json();
  return json(payload, { status: response.status });
};
