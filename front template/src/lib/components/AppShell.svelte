<script lang="ts">
  import type { Snippet } from "svelte";
  import type { HeaderLink, SidebarItem } from "$lib/template-data";

  type Props = {
    children?: Snippet;
    headerLinks: HeaderLink[];
    sidebarItems: SidebarItem[];
    appName?: string;
  };

  let { children, headerLinks, sidebarItems, appName = "PDF Vault" }: Props = $props();

  let sidebarOpen = $state(false);
  let searchTerm = $state("");
  let darkMode = $state(false);

  const isActive = (href: string) => {
    if (typeof window === "undefined") return false;
    const current = `${window.location.pathname}${window.location.search}`;
    return current === href || (href !== "/" && current.startsWith(href));
  };

  const closeSidebar = () => {
    sidebarOpen = false;
  };

  const toggleTheme = () => {
    darkMode = !darkMode;
    if (typeof document === "undefined") return;
    document.documentElement.classList.toggle("dark", darkMode);
    localStorage.setItem("front-template:theme", darkMode ? "dark" : "light");
  };

  const clearSearch = () => {
    searchTerm = "";
  };

  $effect(() => {
    if (typeof document === "undefined") return;
    const stored = localStorage.getItem("front-template:theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    darkMode = stored ? stored === "dark" : prefersDark;
    document.documentElement.classList.toggle("dark", darkMode);
  });
</script>

<div class="flex min-h-svh w-full bg-background text-foreground">
  <button
    type="button"
    class={`fixed inset-0 z-30 bg-black/40 md:hidden ${sidebarOpen ? "block" : "hidden"}`}
    aria-label="Close sidebar"
    onclick={closeSidebar}
  ></button>

  <aside
    class={`fixed inset-y-0 left-0 z-40 w-[var(--sidebar-width)] border-r bg-sidebar text-sidebar-foreground transition-transform md:static md:translate-x-0 ${
      sidebarOpen ? "translate-x-0" : "-translate-x-full"
    }`}
  >
    <div class="flex h-[var(--app-header-height)] items-center gap-3 border-b px-4">
      <div class="flex size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
        P
      </div>
      <div class="flex min-w-0 flex-col leading-none">
        <span class="truncate text-sm font-semibold">{appName}</span>
        <span class="text-xs text-muted-foreground">Template shell</span>
      </div>
    </div>

    <div class="flex h-[calc(100svh-var(--app-header-height))] flex-col overflow-hidden">
      <nav class="flex-1 space-y-1 overflow-y-auto px-2 py-3">
        {#each sidebarItems as item (item.id)}
          <div class="rounded-md p-1">
            <a
              href={item.href}
              class={`block rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                isActive(item.href)
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "hover:bg-sidebar-accent/60"
              }`}
            >
              {item.title}
            </a>

            {#if item.children?.length}
              <div class="mt-1 space-y-1 pl-3">
                {#each item.children as child (child.id)}
                  <a
                    href={child.href}
                    class={`block rounded-md px-3 py-1.5 text-sm transition-colors ${
                      isActive(child.href)
                        ? "bg-sidebar-accent text-sidebar-accent-foreground"
                        : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
                    }`}
                  >
                    {child.title}
                  </a>
                {/each}
              </div>
            {/if}
          </div>
        {/each}
      </nav>

      <div class="border-t p-3">
        <div class="grid grid-cols-2 gap-2">
          <button type="button" class="rounded-md border px-2 py-1.5 text-xs hover:bg-sidebar-accent">
            Edit
          </button>
          <button type="button" class="rounded-md border px-2 py-1.5 text-xs hover:bg-sidebar-accent">
            Add section
          </button>
        </div>
      </div>
    </div>
  </aside>

  <main class="flex min-h-svh min-w-0 flex-1 flex-col">
    <header class="flex h-[var(--app-header-height)] items-center justify-between gap-2 border-b px-4">
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="inline-flex h-9 w-9 items-center justify-center rounded-md border md:hidden"
          aria-label="Toggle sidebar"
          onclick={() => (sidebarOpen = !sidebarOpen)}
        >
          ☰
        </button>

        <nav class="flex items-center gap-1">
          {#each headerLinks as link (link.href)}
            <a
              href={link.href}
              class={`rounded-md px-3 py-2 text-sm transition-colors ${
                isActive(link.href) ? "bg-accent text-accent-foreground" : "hover:bg-accent/60"
              }`}
            >
              {link.label}
            </a>
          {/each}
        </nav>
      </div>

      <div class="flex items-center gap-2">
        <div class="relative hidden sm:block">
          <input
            class="h-9 w-60 rounded-md border bg-background px-3 pr-8 text-sm"
            placeholder="Поиск..."
            bind:value={searchTerm}
          />
          {#if searchTerm}
            <button
              type="button"
              class="absolute inset-y-0 right-2 text-xs text-muted-foreground hover:text-foreground"
              onclick={clearSearch}
            >
              ✕
            </button>
          {/if}
        </div>

        <button
          type="button"
          class="inline-flex h-9 w-9 items-center justify-center rounded-md border"
          aria-label="Toggle theme"
          onclick={toggleTheme}
        >
          {darkMode ? "☾" : "☀"}
        </button>
        <button type="button" class="rounded-md border px-3 py-1.5 text-sm hover:bg-accent/60">Login</button>
      </div>
    </header>

    <div class="flex min-h-0 flex-1 flex-col">
      {@render children?.()}
    </div>
  </main>
</div>
