import type { LayoutLoad } from "./$types";

type AuthSession = {
  is_authenticated: boolean;
  user: {
    id: number;
    username: string;
    email: string;
  } | null;
  users_exist?: boolean;
  site_version?: string;
};

export const ssr = false;

export const load: LayoutLoad = async ({ fetch }) => {
  let auth: AuthSession = {
    is_authenticated: false,
    user: null
  };
  let siteVersion = "unknown";
  let backendDown = false;
  let databaseDown = false;

  try {
    const sessionResponse = await fetch("/api/auth/session/");
    if (sessionResponse.ok) {
      auth = (await sessionResponse.json()) as AuthSession;
      siteVersion = auth.site_version?.trim() || siteVersion;
    } else if (sessionResponse.status >= 500) {
      // Django ответил HTML-страницей ошибки (живой процесс, но 500) — считаем,
      // что недоступна БД. Иначе это ответ прокси (dev), когда Django не запущен.
      const contentType = sessionResponse.headers.get("content-type") ?? "";
      databaseDown = contentType.includes("text/html");
      backendDown = !databaseDown;
    }
  } catch {
    backendDown = true;
  }

  return { auth, siteVersion, backendDown, databaseDown };
};
