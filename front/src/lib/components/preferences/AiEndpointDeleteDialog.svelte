<script lang="ts">
  import * as AlertDialog from "$lib/components/ui/alert-dialog";
  import { deleteAiEndpoint, type AiEndpoint } from "$lib/aiEndpoints";

  type Props = {
    open: boolean;
    endpoint: AiEndpoint | null;
    ondeleted: () => void;
    oncancel: () => void;
  };

  let { open = $bindable(), endpoint = null, ondeleted, oncancel }: Props = $props();

  let deleting = $state(false);
  let errorMessage = $state("");

  async function handleDelete(event: Event) {
    event.preventDefault();
    if (!endpoint) {
      return;
    }
    deleting = true;
    errorMessage = "";
    try {
      await deleteAiEndpoint(endpoint.id);
      ondeleted();
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : "Не удалось удалить endpoint.";
    } finally {
      deleting = false;
    }
  }
</script>

<AlertDialog.Root bind:open onOpenChange={(value) => { if (!value && !deleting) oncancel(); }}>
  <AlertDialog.Content>
    <AlertDialog.Header>
      <AlertDialog.Title>Удаление AI endpoint</AlertDialog.Title>
      <AlertDialog.Description>
        Удалить endpoint «{endpoint?.name ?? ""}»?
        <span class="text-muted-foreground mt-1 block text-xs">
          {#if endpoint?.is_selected}
            Он сейчас выбран — AI переключится на первый оставшийся endpoint, а если список опустеет, AI
            будет выключен.
          {:else}
            Остальные endpoints и настройки Preferences не изменятся.
          {/if}
        </span>
      </AlertDialog.Description>
    </AlertDialog.Header>

    {#if errorMessage}
      <div class="border-destructive/40 bg-destructive/10 text-destructive rounded-xl border px-4 py-3 text-sm">
        {errorMessage}
      </div>
    {/if}

    <AlertDialog.Footer>
      <AlertDialog.Cancel onclick={() => oncancel()} disabled={deleting}>Отмена</AlertDialog.Cancel>
      <AlertDialog.Action
        onclick={handleDelete}
        disabled={deleting}
        class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
      >
        {deleting ? "Удаление..." : "Удалить"}
      </AlertDialog.Action>
    </AlertDialog.Footer>
  </AlertDialog.Content>
</AlertDialog.Root>
