import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { applyDjangoCookies, djangoFetch } from "$lib/server/django";

export const GET: RequestHandler = async (event) => {
  try {
    const response = await djangoFetch(event, "/api/core/preferences");
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

export const PUT: RequestHandler = async (event) => {
  try {
    const body = await event.request.text();
    const response = await djangoFetch(event, "/api/core/preferences", {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body
    });
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
