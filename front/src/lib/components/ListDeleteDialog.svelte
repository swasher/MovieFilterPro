<script lang="ts">
  import * as AlertDialog from "$lib/components/ui/alert-dialog";

  type Props = {
    open: boolean;
    listId: number;
    listName: string;
    ondelete: (id: number) => void;
    oncancel: () => void;
  };

  let { open = $bindable(), listId, listName, ondelete, oncancel }: Props = $props();
  let deleting = $state(false);

  async function handleDelete(e: Event) {
    e.preventDefault();
    deleting = true;
    try {
      const res = await fetch(`/api/vault/lists/${listId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        ondelete(listId);
      }
    } finally {
      deleting = false;
    }
  }
</script>

<AlertDialog.Root bind:open onOpenChange={(v) => { if (!v && !deleting) oncancel(); }}>
  <AlertDialog.Content>
    <AlertDialog.Header>
      <AlertDialog.Title>Удаление списка</AlertDialog.Title>
      <AlertDialog.Description>
        Вы уверены, что хотите удалить список «{listName}»?
        <span class="text-muted-foreground mt-1 block text-xs">Фильмы останутся в Vault, будут удалены только теги из этого списка.</span>
      </AlertDialog.Description>
    </AlertDialog.Header>
    <AlertDialog.Footer>
      <AlertDialog.Cancel onclick={() => oncancel()} disabled={deleting}>Отмена</AlertDialog.Cancel>
      <AlertDialog.Action onclick={handleDelete} disabled={deleting} class="bg-destructive text-destructive-foreground hover:bg-destructive/90">
        {deleting ? "Удаление..." : "Удалить"}
      </AlertDialog.Action>
    </AlertDialog.Footer>
  </AlertDialog.Content>
</AlertDialog.Root>
