<script lang="ts">
  import * as Select from "$lib/components/ui/select";
  import { getAiEndpointsStore } from "./aiEndpointsStore.svelte.js";
  import { getPreferencesStore } from "./store.svelte.js";

  const aiStore = getAiEndpointsStore();
  const store = getPreferencesStore();

  // Значение селекта "по умолчанию": stage-specific endpoint не выбран,
  // используется выбранный endpoint из раздела AI.
  const DEFAULT_VALUE = "default";

  const sortedEndpoints = $derived(
    [...aiStore.endpoints].sort((left, right) => left.name.localeCompare(right.name, "ru"))
  );
  const endpointById = $derived(
    new Map(sortedEndpoints.map((endpoint) => [String(endpoint.id), endpoint]))
  );

  const fastValue = $derived(store.form.kinorium_fast_ai_endpoint_id || DEFAULT_VALUE);
  const deepValue = $derived(store.form.kinorium_deep_ai_endpoint_id || DEFAULT_VALUE);

  const setEndpoint = (
    field: "kinorium_fast_ai_endpoint_id" | "kinorium_deep_ai_endpoint_id",
    value: string | undefined
  ) => {
    store.form[field] = !value || value === DEFAULT_VALUE ? "" : value;
    store.markDirty();
  };

  const selectedInfo = (value: string) => {
    const endpoint = endpointById.get(value);
    if (!endpoint) return "";
    return `${endpoint.model} · ${endpoint.base_url}`;
  };
</script>

<div class="space-y-4">
  <div class="text-muted-foreground text-sm">
    TMDB-матчинг фильмов Kinorium использует две AI-стадии. Для каждой можно выбрать свой endpoint —
    например, быстрый облачный для попарного сравнения сюжетов и мощный для финального выбора.
    Если не выбрано — используется endpoint из раздела AI.
  </div>

  {#if !sortedEndpoints.length}
    <div class="border-destructive/40 bg-destructive/10 text-destructive rounded-xl border px-4 py-3 text-sm">
      Endpoints пока нет — добавьте их в разделе AI, иначе AI-матчинг работать не будет.
    </div>
  {/if}

  <div class="space-y-2">
    <div class="text-sm font-medium">AI для быстрых решений</div>
    <div class="text-muted-foreground text-xs">
      Попарное сравнение сюжета с каждым кандидатом TMDB (fast-стадия). Здесь хорошо работает быстрая
      модель.
    </div>
    <Select.Root
      type="single"
      value={fastValue}
      onValueChange={(value) => setEndpoint("kinorium_fast_ai_endpoint_id", value)}
      disabled={!sortedEndpoints.length}
    >
      <Select.Trigger class="w-full" aria-label="AI для быстрых решений">
        {fastValue === DEFAULT_VALUE
          ? "По умолчанию — выбранный AI endpoint"
          : endpointById.get(fastValue)?.name ?? "—"}
      </Select.Trigger>
      <Select.Content>
        <Select.Item value={DEFAULT_VALUE}>По умолчанию — выбранный AI endpoint</Select.Item>
        {#each sortedEndpoints as endpoint (endpoint.id)}
          <Select.Item value={String(endpoint.id)}>{endpoint.name}</Select.Item>
        {/each}
      </Select.Content>
    </Select.Root>
    {#if fastValue !== DEFAULT_VALUE && selectedInfo(fastValue)}
      <div class="text-muted-foreground truncate text-xs">{selectedInfo(fastValue)}</div>
    {/if}
  </div>

  <div class="space-y-2">
    <div class="text-sm font-medium">AI для глубоких решений</div>
    <div class="text-muted-foreground text-xs">
      Выбор лучшего кандидата из всей кучи и независимая проверка победителя по сюжетам (deep-стадия).
      Здесь важнее качество, чем скорость.
    </div>
    <Select.Root
      type="single"
      value={deepValue}
      onValueChange={(value) => setEndpoint("kinorium_deep_ai_endpoint_id", value)}
      disabled={!sortedEndpoints.length}
    >
      <Select.Trigger class="w-full" aria-label="AI для глубоких решений">
        {deepValue === DEFAULT_VALUE
          ? "По умолчанию — выбранный AI endpoint"
          : endpointById.get(deepValue)?.name ?? "—"}
      </Select.Trigger>
      <Select.Content>
        <Select.Item value={DEFAULT_VALUE}>По умолчанию — выбранный AI endpoint</Select.Item>
        {#each sortedEndpoints as endpoint (endpoint.id)}
          <Select.Item value={String(endpoint.id)}>{endpoint.name}</Select.Item>
        {/each}
      </Select.Content>
    </Select.Root>
    {#if deepValue !== DEFAULT_VALUE && selectedInfo(deepValue)}
      <div class="text-muted-foreground truncate text-xs">{selectedInfo(deepValue)}</div>
    {/if}
  </div>
</div>
