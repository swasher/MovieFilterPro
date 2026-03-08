import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { djangoFetch } from "$lib/server/django";

export const POST: RequestHandler = async (event) => {
  const response = await djangoFetch(event, `/api/kinozal/torrents/${event.params.id}/download`, {
    method: "POST"
  });

  const payload = await response.json();
  return json(payload, { status: response.status });
};
