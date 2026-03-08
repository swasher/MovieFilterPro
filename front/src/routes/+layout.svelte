<script lang="ts">
  import AppShell from "$lib/components/AppShell.svelte";
  import { headerLinks } from "$lib/template-data";
  import { Toaster } from "$lib/components/ui/sonner";
  import "./layout.css";
  import favicon from "$lib/assets/favicon.svg";

  let { children, data } = $props();
</script>

<svelte:head>
  <link rel="icon" href={favicon} />
</svelte:head>

<Toaster />
<AppShell {headerLinks} sidebarItems={data.sidebarItems} auth={data.auth} appName="MovieFilter Pro">
  {@render children?.()}
</AppShell>
