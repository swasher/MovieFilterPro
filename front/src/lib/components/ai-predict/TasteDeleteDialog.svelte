<script lang="ts">
  import * as AlertDialog from "$lib/components/ui/alert-dialog";
  import { deleteTasteProfile, type TasteProfile } from "$lib/aiPredict";

  type Props = {
    open: boolean;
    profile: TasteProfile | null;
    ondeleted: (id: number) => void;
    oncancel: () => void;
  };

  let { open = $bindable(), profile = null, ondeleted, oncancel }: Props = $props();

  let deleting = $state(false);
  let errorMessage = $state("");

  async function handleDelete(event: Event) {
    event.preventDefault();
    if (!profile) {
      return;
    }
    deleting = true;
    errorMessage = "";
    try {
      await deleteTasteProfile(profile.id);
      ondeleted(profile.id);
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : "Не удалось удалить профиль.";
    } finally {
      deleting = false;
    }
  }
</script>

<AlertDialog.Root bind:open onOpenChange={(value) => { if (!value && !deleting) oncancel(); }}>
  <AlertDialog.Content>
    <AlertDialog.Header>
      <AlertDialog.Title>Удаление профиля вкусов</AlertDialog.Title>
      <AlertDialog.Description>
        Удалить профиль «{profile?.name ?? ""}»?
        <span class="text-muted-foreground mt-1 block text-xs">
          История AI-предсказаний останется, но потеряет привязку к профилю.
        </span>
      </AlertDialog.Description>
    </AlertDialog.Header>

    {#if errorMessage}
      <div class="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
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
