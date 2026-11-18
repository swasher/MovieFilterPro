<script lang="ts">
  import { Label } from "$lib/components/ui/label";
  import { Switch } from "$lib/components/ui/switch";
  import { Textarea } from "$lib/components/ui/textarea";
  import { getPreferencesStore } from "./store.svelte.js";

  const store = getPreferencesStore();

  // Пример правил нужен только как подсказка: если поле пустое, кнопка
  // «Смотреть» на странице фильма ничего не откроет.
  const PATH_MAP_PLACEHOLDER = `/share/Movies => \\\\qnap\\Movies
/share/CACHEDEV3_DATA/Review => \\\\qnap\\Review`;
</script>

<div class="space-y-6">
  <div class="flex items-center justify-between gap-4">
    <div>
      <Label for="player-enabled" class="text-sm font-medium">Кнопка «Смотреть»</Label>
      <div class="text-muted-foreground text-xs">
        Вкл — на странице фильма появляется кнопка запуска VLC на вашем компьютере. VLC открывает
        файл напрямую с шары, сервер не отдаёт видео и не перекодирует его.
      </div>
    </div>
    <Switch
      id="player-enabled"
      bind:checked={store.form.player_enabled}
      onCheckedChange={(v) => {
        store.form.player_enabled = v;
        store.markDirty();
        return v;
      }}
    />
  </div>

  <div class="space-y-2">
    <Label for="player-path-map" class="text-sm font-medium">Маппинг путей Plex → UNC</Label>
    <div class="text-muted-foreground text-xs">
      По одному правилу на строку: <code class="font-mono">префикс пути Plex =&gt; префикс UNC</code>.
      Выигрывает самое длинное совпадение, строки с <code class="font-mono">#</code> — комментарии.
    </div>
    <Textarea
      id="player-path-map"
      rows={6}
      class="font-mono text-xs"
      placeholder={PATH_MAP_PLACEHOLDER}
      bind:value={store.form.player_path_map}
      oninput={() => store.markDirty()}
    />
    <div class="text-muted-foreground text-xs">
      Plex внутри контейнера видит шары как <code class="font-mono">/share/&lt;шара&gt;</code>, а
      VLC на Windows открывает <code class="font-mono">\\qnap\&lt;шара&gt;</code>. Обработчик
      протокола <code class="font-mono">mfp://</code> ставится один раз — см.
      <code class="font-mono">player/README.md</code>.
    </div>
  </div>
</div>
