import type { LayoutLoad } from "./$types";
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

export type SystemLabels = Record<string, string>;

export const load: LayoutLoad = async ({ fetch }) => {
  try {
    const response = await fetch("/api/vault/sidebar");
    if (!response.ok) {
      return {
        sidebarItems: defaultSidebarItems satisfies SidebarItem[],
        systemLabels: {} as SystemLabels
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

    const systemLabels: SystemLabels = {};
    for (const group of data) {
      for (const item of group.children) {
        if (["watched", "will_watch", "wont_watch", "favorites"].includes(item.id)) {
          systemLabels[item.id] = item.title;
        }
      }
    }

    return { sidebarItems, systemLabels };
  } catch {
    return {
      sidebarItems: defaultSidebarItems satisfies SidebarItem[],
      systemLabels: {} as SystemLabels
    };
  }
};
