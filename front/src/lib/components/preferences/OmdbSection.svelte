<script lang="ts">
  import { Input } from "$lib/components/ui/input";
  import { getPreferencesStore } from "./store.svelte.js";

  const store = getPreferencesStore();
</script>

<div class="space-y-2">
  <div class="text-sm font-medium">OMDB API key</div>
  <Input bind:value={store.form.omdb_api_key} placeholder="OMDB API key" />
</div>
