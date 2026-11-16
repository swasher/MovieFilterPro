<script lang="ts">
  import MinusIcon from "@lucide/svelte/icons/minus";
  import PencilIcon from "@lucide/svelte/icons/pencil";
  import PlusIcon from "@lucide/svelte/icons/plus";
  import { toast } from "svelte-sonner";
  import TasteProfileDialog from "$lib/components/ai-predict/TasteProfileDialog.svelte";
  import TasteDeleteDialog from "$lib/components/ai-predict/TasteDeleteDialog.svelte";
  import SystemPromptDialog from "$lib/components/ai-predict/SystemPromptDialog.svelte";
  import { Button } from "$lib/components/ui/button";
  import * as Select from "$lib/components/ui/select";
  import {
    getPreferredTasteId,
    resolveTasteProfile,
    setPreferredTasteId,
    type TasteProfile
  } from "$lib/aiPredict";

  type Props = {
    tastes?: TasteProfile[];
    tastesError?: string;
  };

  let { tastes: tastesProp = [], tastesError = "" }: Props = $props();

  let tastes = $state<TasteProfile[]>([]);
  let selectedTasteId = $state<number | null>(null);
  let tasteDialogOpen = $state(false);
  let tasteDialogProfile = $state<TasteProfile | null>(null);
  let deleteTasteOpen = $state(false);
  let systemPromptOpen = $state(false);

  const selectedTaste = $derived(tastes.find((item) => item.id === selectedTasteId) ?? null);

  const sortTastes = (items: TasteProfile[]) =>
    [...items].sort((left, right) => left.name.localeCompare(right.name, "ru"));

  $effect(() => {
    const nextTastes = sortTastes(tastesProp ?? []);
    tastes = nextTastes;
    selectedTasteId = resolveTasteProfile(nextTastes, getPreferredTasteId())?.id ?? null;
  });

  const selectTaste = (id: number | null) => {
    selectedTasteId = id;
    setPreferredTasteId(id);
  };

  const handleTasteChange = (value: string) => {
    const parsed = Number.parseInt(value, 10);
    selectTaste(Number.isFinite(parsed) ? parsed : null);
  };

  const openCreateTaste = () => {
    tasteDialogProfile = null;
    tasteDialogOpen = true;
  };

  const openEditTaste = () => {
    if (!selectedTaste) return;
    tasteDialogProfile = selectedTaste;
    tasteDialogOpen = true;
  };

  const handleTasteSaved = (saved: TasteProfile) => {
    const exists = tastes.some((item) => item.id === saved.id);
    tastes = sortTastes(
      exists ? tastes.map((item) => (item.id === saved.id ? saved : item)) : [...tastes, saved]
    );
    selectTaste(saved.id);
    tasteDialogOpen = false;
    toast.success(exists ? "Профиль вкусов сохранён." : "Профиль вкусов добавлен.");
  };

  const handleTasteDeleted = (id: number) => {
    tastes = tastes.filter((item) => item.id !== id);
    deleteTasteOpen = false;
    if (selectedTasteId === id) {
      selectTaste(resolveTasteProfile(tastes, getPreferredTasteId())?.id ?? null);
    }
    toast.success("Профиль вкусов удалён.");
  };
</script>

<div class="space-y-4">
  {#if tastesError}
    <div class="border-destructive/40 bg-destructive/10 text-destructive rounded-xl border px-4 py-3 text-sm">
      {tastesError}
    </div>
  {/if}

  <div class="space-y-2">
    <div class="text-sm font-medium">AI system prompt</div>
    <Button variant="outline" size="sm" onclick={() => (systemPromptOpen = true)}>Edit</Button>
  </div>

  <div class="space-y-2">
    <div class="text-sm font-medium">Профиль</div>
    <div class="flex gap-2">
      <Select.Root
        type="single"
        value={selectedTasteId === null ? "" : String(selectedTasteId)}
        onValueChange={handleTasteChange}
        disabled={!tastes.length}
      >
        <Select.Trigger class="flex-1" aria-label="Профиль вкусов">
          {#if selectedTaste}
            {selectedTaste.name}
          {:else}
            <span class="text-muted-foreground">
              {tastes.length ? "Выберите профиль" : "Профилей пока нет"}
            </span>
          {/if}
        </Select.Trigger>
        <Select.Content>
          {#each tastes as taste (taste.id)}
            <Select.Item value={String(taste.id)}>{taste.name}</Select.Item>
          {/each}
        </Select.Content>
      </Select.Root>
      <Button variant="outline" size="icon" onclick={openCreateTaste} title="Добавить профиль">
        <PlusIcon class="h-4 w-4" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        onclick={openEditTaste}
        disabled={!selectedTaste}
        title="Редактировать профиль"
      >
        <PencilIcon class="h-4 w-4" />
      </Button>
      <Button
        variant="destructive-outline"
        size="icon"
        onclick={() => (deleteTasteOpen = true)}
        disabled={!selectedTaste}
        title="Удалить профиль"
      >
        <MinusIcon class="h-4 w-4" />
      </Button>
    </div>
  </div>

  {#if !tastes.length}
    <div class="text-muted-foreground text-sm">
      Добавьте профиль кнопкой «+»: вставьте текст или загрузите .md файл.
    </div>
  {/if}

  <TasteProfileDialog
    bind:open={tasteDialogOpen}
    profile={tasteDialogProfile}
    onSaved={handleTasteSaved}
    onCancel={() => (tasteDialogOpen = false)}
  />

  <TasteDeleteDialog
    bind:open={deleteTasteOpen}
    profile={selectedTaste}
    ondeleted={handleTasteDeleted}
    oncancel={() => (deleteTasteOpen = false)}
  />

  <SystemPromptDialog bind:open={systemPromptOpen} onClose={() => (systemPromptOpen = false)} />
</div>
