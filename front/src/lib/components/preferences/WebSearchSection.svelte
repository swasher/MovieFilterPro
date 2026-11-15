<script lang="ts">
  import { Input } from "$lib/components/ui/input";
  import { getPreferencesStore } from "./store.svelte.js";

  const store = getPreferencesStore();
</script>

<div class="grid gap-4 md:grid-cols-2">
  <div class="space-y-2">
    <div class="text-sm font-medium">SearXNG URL</div>
    <Input bind:value={store.form.searxng_url} placeholder="http://localhost:8087/search" />
    <div class="text-muted-foreground text-xs">
      {store.form.searxng_url.trim() ? "Активный провайдер: SearXNG" : "Пусто — используется Tavily"}
    </div>
  </div>
  <div class="space-y-2">
    <div class="text-sm font-medium">Tavily API key</div>
    <Input bind:value={store.form.tavily_api_key} type="password" placeholder="tvly-..." />
  </div>
</div>
