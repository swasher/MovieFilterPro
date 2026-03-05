import { env } from "$env/dynamic/private";
import type { LayoutServerLoad } from "./$types";
import { defaultSidebarItems, type SidebarItem } from "$lib/template-data";

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

const API_BASE_URL = env.API_BASE_URL ?? "http://127.0.0.1:8000";

export const load: LayoutServerLoad = async ({ fetch }) => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/vault/sidebar`);
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
