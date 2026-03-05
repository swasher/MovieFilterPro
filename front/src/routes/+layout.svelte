<script lang="ts">
  import AppShell from "$lib/components/AppShell.svelte";
  import { headerLinks } from "$lib/template-data";
  import "./layout.css";
  import favicon from "$lib/assets/favicon.svg";

  let { children, data } = $props();
</script>

<svelte:head>
  <link rel="icon" href={favicon} />
</svelte:head>

<AppShell {headerLinks} sidebarItems={data.sidebarItems} appName="MovieFilter Pro">
  {@render children?.()}
</AppShell>
