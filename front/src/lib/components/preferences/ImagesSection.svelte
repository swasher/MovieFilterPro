<script lang="ts">
  import { Label } from "$lib/components/ui/label";
  import { Switch } from "$lib/components/ui/switch";
  import { getPreferencesStore } from "./store.svelte.js";

  const store = getPreferencesStore();
</script>

<div class="flex items-center justify-between gap-4">
  <div>
    <Label for="vault-image-cache" class="text-sm font-medium">Дисковый кеш изображений</Label>
    <div class="text-muted-foreground text-xs">
      Вкл — картинки идут через Vault и кешируются на диске сервера. Выкл — напрямую с CDN TMDB с
      обычным браузерным кешированием.
    </div>
  </div>
  <Switch
    id="vault-image-cache"
    bind:checked={store.form.vault_image_cache_enabled}
    onCheckedChange={(v) => {
      store.form.vault_image_cache_enabled = v;
      store.markDirty();
      return v;
    }}
  />
</div>
