import type { RequestHandler } from "./$types";
import { djangoFetch } from "$lib/server/django";

type HeaderBag = Headers & {
  getSetCookie?: () => string[];
};

export const POST: RequestHandler = async (event) => {
  const response = await djangoFetch(event, "/api/auth/logout/", {
    method: "POST"
  });

  const headers = new Headers({
    "Content-Type": response.headers.get("Content-Type") ?? "application/json"
  });
  const setCookieHeaders = (response.headers as HeaderBag).getSetCookie?.() ?? [];
  for (const value of setCookieHeaders) {
    headers.append("set-cookie", value);
  }

  return new Response(response.body, {
    status: response.status,
    headers
  });
};
