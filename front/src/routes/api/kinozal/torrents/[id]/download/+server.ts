import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { djangoFetch } from "$lib/server/django";

export const POST: RequestHandler = async (event) => {
  const requestBody = await event.request.text();
  const response = await djangoFetch(event, `/api/kinozal/torrents/${event.params.id}/download`, {
    method: "POST",
    body: requestBody || undefined,
    headers: requestBody ? { "content-type": "application/json" } : undefined
  });

  const payload = await response.json();
  return json(payload, { status: response.status });
};
