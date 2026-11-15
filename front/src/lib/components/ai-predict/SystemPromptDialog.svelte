<script lang="ts">
  import { toast } from "svelte-sonner";
  import * as Dialog from "$lib/components/ui/dialog";
  import { Badge } from "$lib/components/ui/badge";
  import { Button } from "$lib/components/ui/button";
  import { Textarea } from "$lib/components/ui/textarea";
  import {
    fetchPromptState,
    resetPromptState,
    savePromptState,
    type PromptState
  } from "$lib/aiPredict";

  type Props = {
    open: boolean;
    onClose: () => void;
  };

  let { open = $bindable(), onClose }: Props = $props();

  let promptState = $state<PromptState | null>(null);
  let draft = $state("");
  let loading = $state(false);
  let saving = $state(false);
  let errorMessage = $state("");
  let openedOnce = false;

  $effect(() => {
    if (!open) {
      openedOnce = false;
      return;
    }
    if (openedOnce) {
      return;
    }
    openedOnce = true;
    void load();
  });

  function applyState(next: PromptState) {
    promptState = next;
    draft = next.content;
  }

  async function load() {
    loading = true;
    errorMessage = "";
    try {
      applyState(await fetchPromptState());
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : "Не удалось загрузить промпт.";
    } finally {
      loading = false;
    }
  }

  async function handleSave() {
    saving = true;
    errorMessage = "";
    try {
      applyState(await savePromptState(draft));
      toast.success("Системный промпт сохранён.");
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : "Не удалось сохранить промпт.";
      toast.error(errorMessage);
    } finally {
      saving = false;
    }
  }

  async function handleReset() {
    saving = true;
    errorMessage = "";
    try {
      applyState(await resetPromptState());
      toast.success("Восстановлен стандартный промпт.");
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : "Не удалось сбросить промпт.";
      toast.error(errorMessage);
    } finally {
      saving = false;
    }
  }
</script>

<Dialog.Root bind:open onOpenChange={(value) => { if (!value) onClose(); }}>
  <Dialog.Content
    class="sm:max-w-3xl max-h-[calc(100dvh-2rem)] grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden"
    interactOutsideBehavior="ignore"
    escapeKeydownBehavior="ignore"
  >
    <Dialog.Header>
      <Dialog.Title>AI system prompt</Dialog.Title>
      <Dialog.Description>
        Методика оценки: как модель читает профиль, шкала и формат ответа. Профиль выбранного
        человека добавляется в конец этого текста автоматически, поэтому личных предпочтений
        здесь быть не должно — им место в профиле вкусов.
      </Dialog.Description>
    </Dialog.Header>

    <div class="min-h-0 space-y-3 overflow-y-auto py-2">
      {#if errorMessage}
        <div class="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {errorMessage}
        </div>
      {/if}

      {#if loading}
        <div class="text-muted-foreground py-10 text-center text-sm">Загрузка промпта…</div>
      {:else}
        <Textarea
          bind:value={draft}
          class="min-h-[360px] font-mono text-xs"
          spellcheck="false"
          aria-label="Системный промпт"
        />

        <div class="flex flex-wrap items-center gap-3">
          <span class="text-muted-foreground text-xs">Символов: {draft.length}</span>
          {#if promptState && !promptState.is_default}
            <Badge variant="secondary">изменён</Badge>
          {/if}
          <Button
            variant="outline"
            size="sm"
            class="ml-auto"
            onclick={handleReset}
            disabled={saving || !promptState || promptState.is_default}
          >
            Вернуть стандартный
          </Button>
        </div>
      {/if}
    </div>

    <Dialog.Footer>
      <Button variant="outline" onclick={() => onClose()} disabled={saving}>Закрыть</Button>
      <Button
        onclick={handleSave}
        disabled={saving || loading || !draft.trim() || draft === promptState?.content}
      >
        {saving ? "Сохранение..." : "Сохранить"}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
