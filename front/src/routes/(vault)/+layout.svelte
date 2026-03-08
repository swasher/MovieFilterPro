<script lang="ts">
  import VaultSidebarLayout from "$lib/components/VaultSidebarLayout.svelte";

  let { children, data } = $props();
</script>

<VaultSidebarLayout sidebarItems={data.sidebarItems}>
  {@render children?.()}
</VaultSidebarLayout>
