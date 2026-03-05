import { env } from "$env/dynamic/private";
import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";

const API_BASE_URL = env.API_BASE_URL ?? "http://127.0.0.1:8000";

export const POST: RequestHandler = async ({ params, request, fetch }) => {
  let forceRematch = false;
  try {
    const body = (await request.json()) as { force_rematch?: boolean };
    forceRematch = Boolean(body.force_rematch);
  } catch {
    forceRematch = false;
  }

  const response = await fetch(`${API_BASE_URL}/api/vault/movies/${params.slug}/fetch-tmdb`, {
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
