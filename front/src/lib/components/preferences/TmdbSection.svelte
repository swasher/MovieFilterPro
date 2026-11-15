<script lang="ts">
  import { Input } from "$lib/components/ui/input";
  import { getPreferencesStore } from "./store.svelte.js";

  const store = getPreferencesStore();
</script>

<div class="grid gap-4 md:grid-cols-2">
  <div class="space-y-2">
    <div class="text-sm font-medium">TMDB API key</div>
    <Input bind:value={store.form.tmdb_api_key} placeholder="TMDB API key" />
  </div>
  <div class="space-y-2">
    <div class="text-sm font-medium">TMDB v4 read access token</div>
    <Input bind:value={store.form.tmdb_v4_read_access_token} placeholder="TMDB read access token" />
  </div>
  <div class="space-y-2 md:col-span-2">
    <div class="text-sm font-medium">TMDB authenticated write token</div>
    <Input value={store.preferences?.tmdb_v4_authenticated_access_token ?? ""} readonly />
  </div>
</div>
