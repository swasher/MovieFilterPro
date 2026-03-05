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
  { label: "PDF", href: "/" },
  { label: "Upload", href: "/upload" },
  { label: "Settings", href: "/settings" },
];

export const sidebarItems: SidebarItem[] = [
  {
    id: "cooking",
    title: "Кулинария",
    href: "/?section=cooking",
    children: [
      { id: "sauces", title: "Соусы", href: "/?section=cooking&subsection=sauces" },
      { id: "grill", title: "Гриль", href: "/?section=cooking&subsection=grill" },
    ],
  },
  {
    id: "work",
    title: "Работа",
    href: "/?section=work",
    children: [
      { id: "contracts", title: "Контракты", href: "/?section=work&subsection=contracts" },
      { id: "notes", title: "Заметки", href: "/?section=work&subsection=notes" },
    ],
  },
  {
    id: "archive",
    title: "Архив",
    href: "/?section=archive",
  },
];
