import type { LayoutServerLoad } from "./$types";
import { defaultSidebarItems, type SidebarItem } from "$lib/template-data";
import { djangoFetch } from "$lib/server/django";

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

export const load: LayoutServerLoad = async (event) => {
  try {
    const response = await djangoFetch(event, "/api/vault/sidebar");
    if (!response.ok) {
      return {
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

    return { sidebarItems };
  } catch {
    return {
      sidebarItems: defaultSidebarItems satisfies SidebarItem[]
    };
  }
};
