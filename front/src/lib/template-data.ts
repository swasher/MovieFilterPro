export type HeaderLink = {
  label: string;
  href: string;
};

export type SidebarItem = {
  id: string;
  title: string;
  href: string;
  children?: SidebarItem[];
};

export const headerLinks: HeaderLink[] = [
  { label: "Vault", href: "/" }
];

export const sidebarItems: SidebarItem[] = [
  {
    id: "vault",
    title: "Vault",
    href: "/",
    children: [
      { id: "movies", title: "Movies", href: "/?section=movies" },
      { id: "lists", title: "Lists", href: "/?section=lists" }
    ]
  }
];
