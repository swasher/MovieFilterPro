import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { djangoFetch } from "$lib/server/django";

export const GET: RequestHandler = async (event) => {
  const response = await djangoFetch(event, `/api/kinozal/movies/${event.params.id}/download-options`);
  const payload = await response.json();
  return json(payload, { status: response.status });
};
