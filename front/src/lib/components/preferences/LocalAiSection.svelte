<script lang="ts">
  import CopyIcon from "@lucide/svelte/icons/copy";
  import KeyRoundIcon from "@lucide/svelte/icons/key-round";
  import MinusIcon from "@lucide/svelte/icons/minus";
  import PencilIcon from "@lucide/svelte/icons/pencil";
  import PlusIcon from "@lucide/svelte/icons/plus";
  import { toast } from "svelte-sonner";
  import {
    listAiEndpoints,
    resolveSelectedEndpoint,
    selectAiEndpoint,
    type AiEndpoint
  } from "$lib/aiEndpoints";
  import { Button } from "$lib/components/ui/button";
  import { Label } from "$lib/components/ui/label";
  import * as Select from "$lib/components/ui/select";
  import { Switch } from "$lib/components/ui/switch";
  import AiEndpointDeleteDialog from "./AiEndpointDeleteDialog.svelte";
  import AiEndpointDialog from "./AiEndpointDialog.svelte";
  import AiEndpointKeyDialog from "./AiEndpointKeyDialog.svelte";
  import { getPreferencesStore } from "./store.svelte.js";

  type Props = {
    endpoints?: AiEndpoint[];
    endpointsError?: string;
  };

  let { endpoints = $bindable([]), endpointsError = "" }: Props = $props();

  const store = getPreferencesStore();

  let dialogOpen = $state(false);
  let dialogMode = $state<"create" | "edit" | "duplicate">("create");
  let dialogEndpoint = $state<AiEndpoint | null>(null);
  let suggestedName = $state("");
  let deleteOpen = $state(false);
  let keyOpen = $state(false);
  let selectingId = $state<number | null>(null);

  const sortedEndpoints = $derived(
    [...endpoints].sort((left, right) => left.name.localeCompare(right.name, "ru"))
  );
  const selectedEndpoint = $derived(resolveSelectedEndpoint(sortedEndpoints));

  const refresh = async () => {
    try {
      endpoints = await listAiEndpoints();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось загрузить AI endpoints.");
    }
  };

  const selectEndpoint = async (value: string) => {
    const parsed = Number.parseInt(value, 10);
    if (!Number.isFinite(parsed) || parsed === selectedEndpoint?.id) return;
    selectingId = parsed;
    try {
      await selectAiEndpoint(parsed);
      endpoints = endpoints.map((endpoint) => ({
        ...endpoint,
        is_selected: endpoint.id === parsed
      }));
      toast.success("Выбранный AI переключён.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось переключить AI.");
      // Контролируемый Select мог уйти в новое значение — возвращаем состояние с сервера.
      await refresh();
    } finally {
      selectingId = null;
    }
  };

  const uniqueName = (base: string, existing: string[]) => {
    const used = new Set(existing);
    if (!used.has(base)) return base;
    let index = 2;
    while (used.has(`${base} ${index}`)) index += 1;
    return `${base} ${index}`;
  };

  const openCreate = () => {
    dialogMode = "create";
    dialogEndpoint = null;
    suggestedName = "";
    dialogOpen = true;
  };

  const openEdit = () => {
    if (!selectedEndpoint) return;
    dialogMode = "edit";
    dialogEndpoint = selectedEndpoint;
    suggestedName = "";
    dialogOpen = true;
  };

  const openDuplicate = () => {
    if (!selectedEndpoint) return;
    dialogMode = "duplicate";
    dialogEndpoint = selectedEndpoint;
    suggestedName = uniqueName(
      `${selectedEndpoint.name} copy`,
      endpoints.map((endpoint) => endpoint.name)
    );
    dialogOpen = true;
  };

  const handleSaved = async (_saved: AiEndpoint) => {
    const mode = dialogMode;
    dialogOpen = false;
    // Create/duplicate проходят с select: true — сервер выбирает endpoint
    // в той же транзакции, отдельный запрос не нужен.
    await refresh();
    toast.success(
      mode === "edit"
        ? "AI endpoint сохранён."
        : mode === "duplicate"
          ? "AI endpoint продублирован."
          : "AI endpoint добавлен."
    );
  };

  const handleDeleted = async () => {
    deleteOpen = false;
    await refresh();
    toast.success("AI endpoint удалён.");
  };

  const handleKeySaved = async () => {
    keyOpen = false;
    await refresh();
    toast.success("API-ключ сохранён.");
  };
</script>

<div class="space-y-4">
  {#if endpointsError}
    <div class="border-destructive/40 bg-destructive/10 text-destructive rounded-xl border px-4 py-3 text-sm">
      {endpointsError}
    </div>
  {/if}

  <div class="border-border/70 flex items-center justify-between rounded-xl border px-4 py-3">
    <div class="space-y-1">
      <Label for="ai-enabled" class="text-sm font-medium">AI enabled</Label>
      <div class="text-muted-foreground text-xs">
        Вкл — AI-фичи (скан, TMDB matching, предсказания) используют выбранный endpoint. Выкл — всё без AI.
      </div>
    </div>
    <Switch
      id="ai-enabled"
      bind:checked={store.form.ai_enabled}
      onCheckedChange={(v) => {
        store.form.ai_enabled = v;
        store.markDirty();
        return v;
      }}
    />
  </div>

  <div class="space-y-2">
    <div class="text-sm font-medium">Endpoint</div>
    <div class="flex gap-2">
      <Select.Root
        type="single"
        value={selectedEndpoint ? String(selectedEndpoint.id) : ""}
        onValueChange={selectEndpoint}
        disabled={!sortedEndpoints.length || selectingId !== null}
      >
        <Select.Trigger class="flex-1" aria-label="AI endpoint">
          {#if selectedEndpoint}
            {selectedEndpoint.name}
          {:else}
            <span class="text-muted-foreground">
              {sortedEndpoints.length ? "Выберите endpoint" : "Endpoints пока нет"}
            </span>
          {/if}
        </Select.Trigger>
        <Select.Content>
          {#each sortedEndpoints as endpoint (endpoint.id)}
            <Select.Item value={String(endpoint.id)}>{endpoint.name}</Select.Item>
          {/each}
        </Select.Content>
      </Select.Root>
      <Button variant="outline" size="icon" onclick={openCreate} title="Добавить endpoint">
        <PlusIcon class="h-4 w-4" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        onclick={openDuplicate}
        disabled={!selectedEndpoint}
        title="Дублировать endpoint"
      >
        <CopyIcon class="h-4 w-4" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        onclick={openEdit}
        disabled={!selectedEndpoint}
        title="Редактировать endpoint"
      >
        <PencilIcon class="h-4 w-4" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        onclick={() => (keyOpen = true)}
        disabled={!selectedEndpoint}
        title="Заменить API-ключ"
      >
        <KeyRoundIcon class="h-4 w-4" />
      </Button>
      <Button
        variant="destructive-outline"
        size="icon"
        onclick={() => (deleteOpen = true)}
        disabled={!selectedEndpoint}
        title="Удалить endpoint"
      >
        <MinusIcon class="h-4 w-4" />
      </Button>
    </div>

    {#if selectedEndpoint}
      <div class="text-muted-foreground space-y-1 text-xs">
        <div class="truncate">Base URL: {selectedEndpoint.base_url}</div>
        <div class="truncate">Model: {selectedEndpoint.model}</div>
      </div>
    {/if}
  </div>

  {#if !sortedEndpoints.length}
    <div class="text-muted-foreground text-sm">
      Добавьте endpoint кнопкой «+»: локальный сервер (Ollama, LM Studio, Lemonade, Unsloth) или облачный
      API (Groq и т.п.).
    </div>
  {/if}

  <AiEndpointDialog
    bind:open={dialogOpen}
    mode={dialogMode}
    endpoint={dialogEndpoint}
    suggestedName={suggestedName}
    onSaved={handleSaved}
    onCancel={() => (dialogOpen = false)}
  />

  <AiEndpointKeyDialog
    bind:open={keyOpen}
    endpoint={selectedEndpoint}
    onsaved={handleKeySaved}
    oncancel={() => (keyOpen = false)}
  />

  <AiEndpointDeleteDialog
    bind:open={deleteOpen}
    endpoint={selectedEndpoint}
    ondeleted={handleDeleted}
    oncancel={() => (deleteOpen = false)}
  />
</div>
