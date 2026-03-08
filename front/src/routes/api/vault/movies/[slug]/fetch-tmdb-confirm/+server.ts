import { env } from "$env/dynamic/private";
import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";

const API_BASE_URL = env.API_BASE_URL ?? "http://127.0.0.1:8000";

export const POST: RequestHandler = async ({ params, request, fetch }) => {
  const payload = await request.json();

  const response = await fetch(`${API_BASE_URL}/api/vault/movies/${params.slug}/fetch-tmdb-confirm`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  const data = await response.json();
  return json(data, { status: response.status });
};
