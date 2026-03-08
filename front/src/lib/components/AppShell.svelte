<script lang="ts">
  import SiteShell from "$lib/components/SiteShell.svelte";
  import type { Snippet } from "svelte";
  import type { HeaderLink } from "$lib/template-data";

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
</script>

<SiteShell {headerLinks} {auth} {siteVersion} {appName}>
  {@render children?.()}
</SiteShell>
