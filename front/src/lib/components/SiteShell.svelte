<script lang="ts">
  import { page } from "$app/state";
  import { invalidateAll } from "$app/navigation";
  import { toast } from "svelte-sonner";
  import type { Snippet } from "svelte";
  import type { HeaderLink } from "$lib/template-data";
  import { Button } from "$lib/components/ui/button";
  import { Separator } from "$lib/components/ui/separator";
  import { Moon, Sun, User, KeyRound, Settings, ShieldCheck, Cable, LogOut, ChevronDown, RefreshCw, List, ScrollText } from "@lucide/svelte";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";

  type Props = {
    children?: Snippet;
    headerLinks: HeaderLink[];
    auth: {
      is_authenticated: boolean;
      user: {
        id: number;
        username: string;
        email: string;
      } | null;
    };
    siteVersion: string;
    appName?: string;
  };

  let { children, headerLinks, auth, siteVersion, appName = "MovieFilter Pro" }: Props = $props();

  let darkMode = $state(false);
  let isLoggingOut = $state(false);

  const isActive = (href: string): boolean => {
    const currentPath = page.url.pathname;
    const currentSearch = page.url.search;

    if (href.includes("?")) {
      return `${currentPath}${currentSearch}` === href;
    }

    return href === "/" ? currentPath === "/" : currentPath === href || currentPath.startsWith(`${href}/`);
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
      const response = await fetch("/api/auth/logout/", {
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

<div class="bg-background flex min-h-svh flex-col">
  <header class="bg-background/95 supports-[backdrop-filter]:bg-background/80 sticky top-0 z-20 border-b backdrop-blur">
    <div class="flex min-h-14 items-center justify-between gap-3 px-3 py-2 md:px-4">
      <div class="flex min-w-0 items-center gap-3">
        <div class="min-w-0">
          <div class="inline-flex items-center rounded-md bg-muted/50 px-2.5 py-1 text-sm font-semibold transition-colors hover:bg-muted/70">
            {appName}
          </div>
        </div>

        <nav class="flex flex-wrap items-center gap-1">
          {#each headerLinks as link (link.href)}
            <Button href={link.href} variant={isActive(link.href) ? "secondary" : "ghost"} size="sm">
              {link.label}
            </Button>
          {/each}
        </nav>
      </div>

      <div class="flex flex-wrap items-center justify-end gap-2">
        <small class="text-muted-foreground text-xs">v. {siteVersion}</small>

        <Button variant="outline" size="icon" onclick={toggleTheme} aria-label="Toggle theme">
          {#if darkMode}
            <Moon class="size-4" />
          {:else}
            <Sun class="size-4" />
          {/if}
        </Button>

        {#if auth.is_authenticated && auth.user}
          {@const user = auth.user}
          <DropdownMenu.Root>
            <DropdownMenu.Trigger>
              {#snippet child({ props })}
                <Button variant="outline" size="sm" {...props}>
                  <User class="size-4" />
                  {user.username}
                  <ChevronDown class="size-3.5 opacity-60 ml-0.5" />
                </Button>
              {/snippet}
            </DropdownMenu.Trigger>
            <DropdownMenu.Content align="end" class="w-48">
              <DropdownMenu.Label class="text-xs font-normal text-muted-foreground">
                Пользователь: <span class="font-semibold text-foreground">{user.username}</span>
              </DropdownMenu.Label>
              <DropdownMenu.Separator />
              <DropdownMenu.Item>
                {#snippet child({ props })}
                  <a href="/preferences" {...props}>
                    <Settings class="mr-2 size-4" />
                    <span>Preferences</span>
                  </a>
                {/snippet}
              </DropdownMenu.Item>
              <DropdownMenu.Separator />
              <DropdownMenu.Group>
                <DropdownMenu.Item>
                  {#snippet child({ props })}
                    <a href="/admin/" target="_blank" rel="noreferrer" {...props}>
                      <ShieldCheck class="mr-2 size-4" />
                      <span>Django Admin</span>
                    </a>
                  {/snippet}
                </DropdownMenu.Item>
                <DropdownMenu.Item>
                  {#snippet child({ props })}
                    <a href="/connections" {...props}>
                      <Cable class="mr-2 size-4" />
                      <span>События связок</span>
                    </a>
                  {/snippet}
                </DropdownMenu.Item>
                <DropdownMenu.Item>
                  {#snippet child({ props })}
                    <a href="/tmdb-sync" {...props}>
                      <RefreshCw class="mr-2 size-4" />
                      <span>TMDB Sync Queue</span>
                    </a>
                  {/snippet}
                </DropdownMenu.Item>
                <DropdownMenu.Item>
                  {#snippet child({ props })}
                    <a href="/tmdb-auth" {...props}>
                      <KeyRound class="mr-2 size-4" />
                      <span>TMDB Auth</span>
                    </a>
                  {/snippet}
                </DropdownMenu.Item>
                <DropdownMenu.Item>
                  {#snippet child({ props })}
                    <a href="/tmdb-writeback" {...props}>
                      <List class="mr-2 size-4" />
                      <span>Write-back Error Log</span>
                    </a>
                  {/snippet}
                </DropdownMenu.Item>
                <DropdownMenu.Item>
                  {#snippet child({ props })}
                    <a href="/match-log" {...props}>
                      <ScrollText class="mr-2 size-4" />
                      <span>Match Log</span>
                    </a>
                  {/snippet}
                </DropdownMenu.Item>
              </DropdownMenu.Group>
              <DropdownMenu.Separator />
              <DropdownMenu.Item onclick={logout} disabled={isLoggingOut}>
                <LogOut class="mr-2 size-4" />
                <span>{isLoggingOut ? "Выход..." : "Выйти"}</span>
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
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

  <main class="flex min-h-0 flex-1 flex-col">
    {@render children?.()}
  </main>
</div>
