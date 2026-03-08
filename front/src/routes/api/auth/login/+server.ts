import type { RequestHandler } from "./$types";
import { djangoFetch } from "$lib/server/django";

type HeaderBag = Headers & {
  getSetCookie?: () => string[];
};

export const POST: RequestHandler = async (event) => {
  const formData = await event.request.formData();
  const body = new URLSearchParams();

  body.set("username", String(formData.get("username") ?? ""));
  body.set("password", String(formData.get("password") ?? ""));

  const response = await djangoFetch(event, "/api/auth/login/", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded"
    },
    body
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
