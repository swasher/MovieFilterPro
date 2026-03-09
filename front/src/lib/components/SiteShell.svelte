<script lang="ts">
  import { page } from "$app/state";
  import { invalidateAll } from "$app/navigation";
  import { toast } from "svelte-sonner";
  import type { Snippet } from "svelte";
  import type { HeaderLink } from "$lib/template-data";
  import { Button } from "$lib/components/ui/button";
  import { Separator } from "$lib/components/ui/separator";
  import { Moon, Sun, User, KeyRound, Settings } from "@lucide/svelte";

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

<div class="bg-background flex min-h-svh flex-col">
  <header class="bg-background/95 supports-[backdrop-filter]:bg-background/80 sticky top-0 z-20 border-b backdrop-blur">
    <div class="flex min-h-14 items-center justify-between gap-3 px-3 py-2 md:px-4">
      <div class="flex min-w-0 items-center gap-3">
        <a href="/" class="flex items-center gap-2">
          <div class="bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-md text-xs font-semibold">
            MF
          </div>
          <div class="min-w-0">
            <p class="truncate text-sm font-semibold">{appName}</p>
          </div>
        </a>

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

        <Button href="/tmdb" variant={isActive("/tmdb") ? "secondary" : "outline"} size="sm">
          <KeyRound class="size-4" />
          TMDB
        </Button>

        <Button href="/preferences" variant={isActive("/preferences") ? "secondary" : "outline"} size="sm">
          <Settings class="size-4" />
          Preferences
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

        <Button variant="outline" size="icon" onclick={toggleTheme} aria-label="Toggle theme">
          {#if darkMode}
            <Moon class="size-4" />
          {:else}
            <Sun class="size-4" />
          {/if}
        </Button>
      </div>
    </div>
    <Separator />
  </header>

  <main class="flex min-h-0 flex-1 flex-col">
    {@render children?.()}
  </main>
</div>
