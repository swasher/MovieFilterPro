import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { applyDjangoCookies, djangoFetch } from "$lib/server/django";

export const GET: RequestHandler = async (event) => {
  try {
    const response = await djangoFetch(event, "/api/kinozal/summary");
    applyDjangoCookies(response, event.cookies);
    const payload = await response.json();
    return json(payload, { status: response.status });
  } catch (error) {
    return json(
      {
        detail: error instanceof Error ? error.message : "Unknown API error"
      },
      { status: 502 }
    );
  }
};
