export type HeaderLink = {
  label: string;
  href: string;
};

export type SidebarItem = {
  id: string;
  title: string;
  href: string;
  count?: number;
  children?: SidebarItem[];
};

export const headerLinks: HeaderLink[] = [
  { label: "Vault", href: "/" },
  { label: "Kinozal", href: "/kinozal" },
  { label: "Plex", href: "/plex" },
  { label: "Scan", href: "/scan" }
];

export const defaultSidebarItems: SidebarItem[] = [
  {
    id: "system",
    title: "Системные",
    href: "#",
    children: [
      { id: "all", title: "Все фильмы", href: "/", count: 0 },
      { id: "watched", title: "Просмотрено", href: "/?status=watched", count: 0 },
      { id: "will_watch", title: "Буду смотреть", href: "/?status=will_watch", count: 0 },
      { id: "wont_watch", title: "Не интересует", href: "/?status=wont_watch", count: 0 },
      { id: "favorites", title: "Избранное", href: "/?status=favorites", count: 0 }
    ]
  },
  {
    id: "custom",
    title: "Мои списки",
    href: "#",
    children: []
  },
  {
    id: "connections",
    title: "Интеграции",
    href: "#",
    children: [{ id: "connection_events", title: "События связок", href: "/connections", count: 0 }]
  }
];
