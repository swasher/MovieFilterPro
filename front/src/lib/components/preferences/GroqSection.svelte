<script lang="ts">
  import { Input } from "$lib/components/ui/input";
  import { getPreferencesStore } from "./store.svelte.js";

  const store = getPreferencesStore();
</script>

<div class="grid gap-4 md:grid-cols-2">
  <div class="space-y-2">
    <div class="text-sm font-medium">Groq API key</div>
    <Input bind:value={store.form.groq_api_key} type="password" placeholder="gsk_..." />
  </div>
  <div class="space-y-2">
    <div class="text-sm font-medium">Groq model</div>
    <Input bind:value={store.form.groq_model} placeholder="llama-3.3-70b-versatile" />
  </div>
</div>
