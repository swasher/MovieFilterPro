<script lang="ts">
  import AppShell from "$lib/components/AppShell.svelte";
  import { headerLinks } from "$lib/template-data";
  import { Toaster } from "$lib/components/ui/sonner";
  import "./layout.css";

  let { children, data } = $props();
</script>

<Toaster position="top-center" />
<AppShell {headerLinks} auth={data.auth} siteVersion={data.siteVersion} appName="MovieFilter Pro">
  {@render children?.()}
</AppShell>
