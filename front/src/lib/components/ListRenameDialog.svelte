<script lang="ts">
  import * as Dialog from "$lib/components/ui/dialog";
  import { Input } from "$lib/components/ui/input";
  import { Button } from "$lib/components/ui/button";

  type Props = {
    open: boolean;
    listId: number;
    listName: string;
    onsave: (id: number, name: string) => void;
    oncancel: () => void;
  };

  let { open = $bindable(), listId, listName, onsave, oncancel }: Props = $props();

  let nameValue = $state("");
  let saving = $state(false);

  $effect(() => {
    if (open) {
      nameValue = listName;
    }
  });

  async function handleSave() {
    const trimmed = nameValue.trim();
    if (!trimmed || trimmed === listName) {
      oncancel();
      return;
    }
    saving = true;
    try {
      const res = await fetch(`/api/vault/lists/${listId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: trimmed }),
      });
      if (res.ok) {
        onsave(listId, trimmed);
      }
    } finally {
      saving = false;
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" && !saving) {
      handleSave();
    }
  }
</script>

<Dialog.Root bind:open onOpenChange={(v) => { if (!v) oncancel(); }}>
  <Dialog.Content class="sm:max-w-md">
    <Dialog.Header>
      <Dialog.Title>Переименование списка</Dialog.Title>
      <Dialog.Description>Введите новое название списка</Dialog.Description>
    </Dialog.Header>
    <div class="py-2">
      <Input
        bind:value={nameValue}
        placeholder="Название списка"
        onkeydown={handleKeydown}
        autofocus
      />
    </div>
    <Dialog.Footer>
      <Button variant="outline" onclick={() => oncancel()} disabled={saving}>Отмена</Button>
      <Button onclick={handleSave} disabled={saving || !nameValue.trim()}>
        {saving ? "Сохранение..." : "Сохранить"}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
