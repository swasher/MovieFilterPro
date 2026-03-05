<script lang="ts">
  import AppShell from "$lib/components/AppShell.svelte";
  import { headerLinks, sidebarItems } from "$lib/template-data";
  import "./layout.css";
  import favicon from "$lib/assets/favicon.svg";

  let { children } = $props();
</script>

<svelte:head>
  <link rel="icon" href={favicon} />
</svelte:head>

<AppShell {headerLinks} {sidebarItems} appName="MovieFilter Pro">
  {@render children?.()}
</AppShell>
