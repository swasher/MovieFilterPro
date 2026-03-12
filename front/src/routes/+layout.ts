import type { LayoutLoad } from "./$types";

type AuthSession = {
  is_authenticated: boolean;
  user: {
    id: number;
    username: string;
    email: string;
  } | null;
  site_version?: string;
};

export const ssr = false;

export const load: LayoutLoad = async ({ fetch }) => {
  let auth: AuthSession = {
    is_authenticated: false,
    user: null
  };
  let siteVersion = "unknown";

  try {
    const sessionResponse = await fetch("/api/auth/session/");
    if (sessionResponse.ok) {
      auth = (await sessionResponse.json()) as AuthSession;
      siteVersion = auth.site_version?.trim() || siteVersion;
    }
  } catch {
    return { auth, siteVersion };
  }

  return { auth, siteVersion };
};
