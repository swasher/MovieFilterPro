<script lang="ts">
  import { invalidateAll } from "$app/navigation";
  import { toast } from "svelte-sonner";
  import type { Snippet } from "svelte";
  import type { HeaderLink, SidebarItem } from "$lib/template-data";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { Badge } from "$lib/components/ui/badge";
  import { Separator } from "$lib/components/ui/separator";
  import * as Sidebar from "$lib/components/ui/sidebar";
  import { Moon, Sun, Search, User, Pencil, Plus } from "@lucide/svelte";

  type Props = {
    children?: Snippet;
    headerLinks: HeaderLink[];
    sidebarItems: SidebarItem[];
    auth: {
      is_authenticated: boolean;
      user: {
        id: number;
        username: string;
        email: string;
      } | null;
    };
    appName?: string;
  };

  let { children, headerLinks, sidebarItems, auth, appName = "MovieFilter Pro" }: Props = $props();

  let searchTerm = $state("");
  let darkMode = $state(false);
  let isLoggingOut = $state(false);

  const isActive = (href: string): boolean => {
    if (typeof window === "undefined") return false;
    const current = `${window.location.pathname}${window.location.search}`;
    return current === href || (href !== "/" && current.startsWith(href));
  };

  const toggleTheme = () => {
    darkMode = !darkMode;
    if (typeof document === "undefined" || typeof window === "undefined") return;
    document.documentElement.classList.toggle("dark", darkMode);
    window.localStorage.setItem("moviefilter:theme", darkMode ? "dark" : "light");
  };

  $effect(() => {
    if (typeof document === "undefined" || typeof window === "undefined") return;
    const stored = window.localStorage.getItem("moviefilter:theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    darkMode = stored ? stored === "dark" : prefersDark;
    document.documentElement.classList.toggle("dark", darkMode);
  });

  const logout = async () => {
    isLoggingOut = true;

    try {
      const response = await fetch("/api/auth/logout", {
        method: "POST"
      });
      const payload = (await response.json()) as { message?: string };
      if (!response.ok) {
        toast.error(payload.message ?? `HTTP ${response.status}`);
        return;
      }

      await invalidateAll();
      toast.success(payload.message ?? "Выход выполнен.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Ошибка выхода");
    } finally {
      isLoggingOut = false;
    }
  };
</script>

<Sidebar.Provider>
  <Sidebar.Root>
    <Sidebar.Header>
      <div class="flex items-center gap-2 px-2 py-1">
        <div class="bg-sidebar-primary text-sidebar-primary-foreground flex size-8 items-center justify-center rounded-md text-xs font-semibold">
          MF
        </div>
        <div class="min-w-0">
          <p class="truncate text-sm font-semibold">{appName}</p>
          <p class="text-muted-foreground text-xs">Frontend shell</p>
        </div>
      </div>
    </Sidebar.Header>

    <Sidebar.Content>
      <Sidebar.Group>
        <Sidebar.GroupLabel>Списки</Sidebar.GroupLabel>
        <Sidebar.GroupContent>
          <Sidebar.Menu>
            {#each sidebarItems as item (item.id)}
              <Sidebar.MenuItem>
                <Sidebar.MenuButton isActive={isActive(item.href)}>
                  {#snippet child({ props })}
                    <a {...props} href={item.href}>
                      <span>{item.title}</span>
                      {#if typeof item.count === "number"}
                        <Badge variant="secondary" class="ml-auto">{item.count}</Badge>
                      {:else if item.children?.length}
                        <Badge variant="secondary" class="ml-auto">{item.children.length}</Badge>
                      {/if}
                    </a>
                  {/snippet}
                </Sidebar.MenuButton>

                {#if item.children?.length}
                  <Sidebar.MenuSub>
                    {#each item.children as subItem (subItem.id)}
                      <Sidebar.MenuSubItem>
                        <Sidebar.MenuSubButton isActive={isActive(subItem.href)}>
                          {#snippet child({ props })}
                            <a {...props} href={subItem.href}>
                              <span>{subItem.title}</span>
                              {#if typeof subItem.count === "number"}
                                <Badge variant="outline" class="ml-auto">{subItem.count}</Badge>
                              {/if}
                            </a>
                          {/snippet}
                        </Sidebar.MenuSubButton>
                      </Sidebar.MenuSubItem>
                    {/each}
                  </Sidebar.MenuSub>
                {/if}
              </Sidebar.MenuItem>
            {/each}
          </Sidebar.Menu>
        </Sidebar.GroupContent>
      </Sidebar.Group>
    </Sidebar.Content>

    <Sidebar.Footer>
      <div class="grid grid-cols-2 gap-2 px-2 py-1">
        <Button variant="outline" size="sm">
          <Pencil class="size-4" />
          Edit
        </Button>
        <Button variant="outline" size="sm">
          <Plus class="size-4" />
          Add
        </Button>
      </div>
    </Sidebar.Footer>

    <Sidebar.Rail />
  </Sidebar.Root>

  <Sidebar.Inset>
    <header class="bg-background/95 supports-[backdrop-filter]:bg-background/80 sticky top-0 z-20 border-b backdrop-blur">
      <div class="flex h-14 items-center justify-between gap-2 px-3 md:px-4">
        <div class="flex items-center gap-2">
          <Sidebar.Trigger class="md:hidden" />
          <nav class="flex items-center gap-1">
            {#each headerLinks as link (link.href)}
              <Button href={link.href} variant={isActive(link.href) ? "secondary" : "ghost"} size="sm">
                {link.label}
              </Button>
            {/each}
          </nav>
        </div>

        <div class="flex items-center gap-2">
          <div class="relative hidden sm:block">
            <Search class="text-muted-foreground pointer-events-none absolute top-1/2 left-2 size-4 -translate-y-1/2" />
            <Input bind:value={searchTerm} placeholder="Поиск..." class="w-56 pl-8" />
          </div>

          <Button variant="outline" size="icon" onclick={toggleTheme} aria-label="Toggle theme">
            {#if darkMode}
              <Moon class="size-4" />
            {:else}
              <Sun class="size-4" />
            {/if}
          </Button>

          {#if auth.is_authenticated && auth.user}
            <div class="flex items-center gap-2">
              <Button variant="outline" size="sm" disabled>
                <User class="size-4" />
                {auth.user.username}
              </Button>
              <Button variant="outline" size="sm" onclick={logout} disabled={isLoggingOut}>
                <User class="size-4" />
                {isLoggingOut ? "..." : "Выйти"}
              </Button>
            </div>
          {:else}
            <Button href="/login" variant="outline" size="sm">
              <User class="size-4" />
              Войти
            </Button>
          {/if}
        </div>
      </div>
      <Separator />
    </header>

    <div class="flex min-h-0 flex-1 flex-col">
      {@render children?.()}
    </div>
  </Sidebar.Inset>
</Sidebar.Provider>
