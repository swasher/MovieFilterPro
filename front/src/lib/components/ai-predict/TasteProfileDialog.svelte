<script lang="ts">
  import * as Dialog from "$lib/components/ui/dialog";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { Textarea } from "$lib/components/ui/textarea";
  import {
    createTasteProfile,
    updateTasteProfile,
    type TasteProfile
  } from "$lib/aiPredict";

  type Props = {
    open: boolean;
    /** null — создание нового профиля, иначе редактирование существующего. */
    profile: TasteProfile | null;
    onSaved: (profile: TasteProfile) => void;
    onCancel: () => void;
  };

  let { open = $bindable(), profile = null, onSaved, onCancel }: Props = $props();

  let nameValue = $state("");
  let contentValue = $state("");
  let errorMessage = $state("");
  let loadedFileName = $state("");
  let saving = $state(false);

  const isEdit = $derived(Boolean(profile));

  $effect(() => {
    if (open) {
      nameValue = profile?.name ?? "";
      contentValue = profile?.content ?? "";
      errorMessage = "";
      loadedFileName = "";
      saving = false;
    }
  });

  async function handleFileChange(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      return;
    }
    try {
      contentValue = await file.text();
      loadedFileName = file.name;
      if (!nameValue.trim()) {
        nameValue = file.name.replace(/\.(md|markdown|txt)$/i, "");
      }
      errorMessage = "";
    } catch {
      errorMessage = "Не удалось прочитать файл.";
    } finally {
      input.value = "";
    }
  }

  async function handleSave() {
    const trimmedName = nameValue.trim();
    if (!trimmedName) {
      errorMessage = "Название профиля не может быть пустым.";
      return;
    }

    saving = true;
    errorMessage = "";
    try {
      const saved = profile
        ? await updateTasteProfile(profile.id, { name: trimmedName, content: contentValue })
        : await createTasteProfile(trimmedName, contentValue);
      onSaved(saved);
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : "Не удалось сохранить профиль.";
    } finally {
      saving = false;
    }
  }
</script>

<Dialog.Root bind:open onOpenChange={(value) => { if (!value) onCancel(); }}>
  <Dialog.Content
    class="sm:max-w-2xl max-h-[calc(100dvh-2rem)] grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden"
    interactOutsideBehavior="ignore"
    escapeKeydownBehavior="ignore"
  >
    <Dialog.Header>
      <Dialog.Title>{isEdit ? "Редактирование профиля вкусов" : "Новый профиль вкусов"}</Dialog.Title>
    </Dialog.Header>

    <div class="min-h-0 space-y-4 overflow-y-auto py-2">
      <div class="space-y-2">
        <div class="text-sm font-medium">Название</div>
        <Input bind:value={nameValue} placeholder="Например, Rita" autofocus />
      </div>

      <div class="space-y-2">
        <div class="flex items-center justify-between gap-3">
          <div class="text-sm font-medium">Профиль</div>
          <div class="flex items-center gap-2">
            {#if loadedFileName}
              <span class="text-muted-foreground max-w-40 truncate text-xs">{loadedFileName}</span>
            {/if}
            <Input
              type="file"
              accept=".md,.markdown,.txt,text/plain,text/markdown"
              class="h-8 w-48 text-xs"
              aria-label="Загрузить профиль из файла"
              onchange={handleFileChange}
            />
          </div>
        </div>
        <Textarea
          bind:value={contentValue}
          class="min-h-[260px] font-mono text-xs"
          placeholder={"Мне нравится:\n- жанры: детективы, триллеры…\n\nМне не нравится:\n- ужасы…"}
        />
        <div class="text-muted-foreground text-xs">Символов: {contentValue.length}</div>
      </div>

      {#if errorMessage}
        <div class="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {errorMessage}
        </div>
      {/if}
    </div>

    <Dialog.Footer>
      <Button variant="outline" onclick={() => onCancel()} disabled={saving}>Отмена</Button>
      <Button onclick={handleSave} disabled={saving || !nameValue.trim()}>
        {saving ? "Сохранение..." : "Сохранить"}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
