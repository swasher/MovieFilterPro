import type { LayoutServerLoad } from "./$types";
import { applyDjangoCookies, djangoFetch } from "$lib/server/django";

type AuthSession = {
  is_authenticated: boolean;
  user: {
    id: number;
    username: string;
    email: string;
  } | null;
  site_version?: string;
};

export const load: LayoutServerLoad = async (event) => {
  let auth: AuthSession = {
    is_authenticated: false,
    user: null
  };
  let siteVersion = "unknown";

  try {
    const sessionResponse = await djangoFetch(event, "/api/auth/session/");
    applyDjangoCookies(sessionResponse, event.cookies);
    if (sessionResponse.ok) {
      auth = (await sessionResponse.json()) as AuthSession;
      siteVersion = auth.site_version?.trim() || siteVersion;
    }
  } catch {
    return { auth, siteVersion };
  }

  return { auth, siteVersion };
};
