<script lang="ts">
  import AppShell from "$lib/components/AppShell.svelte";
  import { headerLinks, sidebarItems } from "$lib/template-data";
  import "./layout.css";

  let { children } = $props();
</script>

<AppShell {headerLinks} {sidebarItems} appName="PDF Vault">
  {@render children?.()}
</AppShell>
