import type { LayoutServerLoad } from "./$types";
import { defaultSidebarItems, type SidebarItem } from "$lib/template-data";
import { applyDjangoCookies, djangoFetch } from "$lib/server/django";

type ApiSidebarItem = {
  id: string;
  title: string;
  href: string;
  count: number;
};

type ApiSidebarGroup = {
  id: string;
  title: string;
  href: string;
  children: ApiSidebarItem[];
};

type AuthSession = {
  is_authenticated: boolean;
  user: {
    id: number;
    username: string;
    email: string;
  } | null;
};

export const load: LayoutServerLoad = async (event) => {
  let auth: AuthSession = {
    is_authenticated: false,
    user: null
  };

  try {
    const sessionResponse = await djangoFetch(event, "/api/auth/session/");
    applyDjangoCookies(sessionResponse, event.cookies);
    if (sessionResponse.ok) {
      auth = (await sessionResponse.json()) as AuthSession;
    }

    const response = await djangoFetch(event, "/api/vault/sidebar");
    if (!response.ok) {
      return {
        auth,
        sidebarItems: defaultSidebarItems satisfies SidebarItem[]
      };
    }

    const data = (await response.json()) as ApiSidebarGroup[];
    const sidebarItems: SidebarItem[] = data.map((group) => ({
      id: group.id,
      title: group.title,
      href: group.href || "#",
      children: group.children.map((item) => ({
        id: item.id,
        title: item.title,
        href: item.href,
        count: item.count
      }))
    }));

    return { auth, sidebarItems };
  } catch {
    return {
      auth,
      sidebarItems: defaultSidebarItems satisfies SidebarItem[]
    };
  }
};
