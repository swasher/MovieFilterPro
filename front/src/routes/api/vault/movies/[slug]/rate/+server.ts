import { env } from "$env/dynamic/private";
import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";

const API_BASE_URL = env.API_BASE_URL ?? "http://127.0.0.1:8000";

export const POST: RequestHandler = async ({ params, request, fetch }) => {
  const body = (await request.json()) as { rating: number | null };
  const response = await fetch(`${API_BASE_URL}/api/vault/movies/${params.slug}/rate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  });

  const payload = await response.json();
  return json(payload, { status: response.status });
};
