import { env } from "$env/dynamic/private";
import type { Cookies, RequestEvent } from "@sveltejs/kit";

const API_BASE_URL = env.API_BASE_URL ?? "http://127.0.0.1:8000";
const DJANGO_COOKIE_NAMES = ["sessionid", "csrftoken"] as const;

type HeaderBag = Headers & {
  getSetCookie?: () => string[];
};

function buildCookieHeader(cookies: Cookies): string {
  return DJANGO_COOKIE_NAMES.map((name) => {
    const value = cookies.get(name);
    return value ? `${name}=${value}` : null;
  })
    .filter(Boolean)
    .join("; ");
}

function parseSetCookieHeader(headerValue: string) {
  const segments = headerValue.split(";").map((item) => item.trim());
  const [nameValue, ...attributes] = segments;
  const separatorIndex = nameValue.indexOf("=");
  if (separatorIndex === -1) {
    return null;
  }

  const name = nameValue.slice(0, separatorIndex);
  const value = nameValue.slice(separatorIndex + 1);
  const normalizedAttributes = attributes.reduce<Record<string, string | true>>((acc, item) => {
    const attrSeparator = item.indexOf("=");
    if (attrSeparator === -1) {
      acc[item.toLowerCase()] = true;
      return acc;
    }

    const attrName = item.slice(0, attrSeparator).toLowerCase();
    const attrValue = item.slice(attrSeparator + 1);
    acc[attrName] = attrValue;
    return acc;
  }, {});

  return {
    name,
    value,
    attributes: normalizedAttributes,
  };
}

export function applyDjangoCookies(response: Response, cookies: Cookies) {
  const headerBag = response.headers as HeaderBag;
  const setCookieHeaders = headerBag.getSetCookie?.() ?? [];

  for (const headerValue of setCookieHeaders) {
    const parsed = parseSetCookieHeader(headerValue);
    if (!parsed || !DJANGO_COOKIE_NAMES.includes(parsed.name as (typeof DJANGO_COOKIE_NAMES)[number])) {
      continue;
    }

    const maxAge = parsed.attributes["max-age"];
    const expires = parsed.attributes.expires;
    const shouldDelete = parsed.value === "" || maxAge === "0";

    if (shouldDelete) {
      cookies.delete(parsed.name, {
        path: "/",
      });
      continue;
    }

    cookies.set(parsed.name, parsed.value, {
      path: "/",
      httpOnly: parsed.name === "sessionid",
      sameSite: "lax",
      secure: false,
      maxAge: typeof maxAge === "string" ? Number(maxAge) : undefined,
      expires: typeof expires === "string" ? new Date(expires) : undefined,
    });
  }
}

export async function djangoFetch(
  event: Pick<RequestEvent, "fetch" | "cookies">,
  path: string,
  init: RequestInit = {},
) {
  const headers = new Headers(init.headers);
  const cookieHeader = buildCookieHeader(event.cookies);

  if (cookieHeader) {
    headers.set("Cookie", cookieHeader);
  }

  const method = (init.method ?? "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
    const csrfToken = event.cookies.get("csrftoken");
    if (csrfToken) {
      headers.set("X-CSRFToken", csrfToken);
    }
  }

  return event.fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  });
}
