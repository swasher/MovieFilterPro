<script lang="ts">
  import { Input } from "$lib/components/ui/input";
  import { getPreferencesStore } from "./store.svelte.js";

  const store = getPreferencesStore();
</script>

<div class="grid gap-4 md:grid-cols-2">
  <div class="space-y-2">
    <div class="text-sm font-medium">Plex address</div>
    <Input bind:value={store.form.plex_address} placeholder="http://plex:32400" />
  </div>
  <div class="space-y-2">
    <div class="text-sm font-medium">Plex token</div>
    <Input bind:value={store.form.plex_token} placeholder="Plex token" />
  </div>
</div>
