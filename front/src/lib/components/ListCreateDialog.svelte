<script lang="ts">
  import * as Dialog from "$lib/components/ui/dialog";
  import { Input } from "$lib/components/ui/input";
  import { Button } from "$lib/components/ui/button";

  type Props = {
    open: boolean;
    oncreate: (name: string, id: number) => void;
    oncancel: () => void;
  };

  let { open = $bindable(), oncreate, oncancel }: Props = $props();

  let nameValue = $state("");
  let saving = $state(false);

  $effect(() => {
    if (open) {
      nameValue = "";
    }
  });

  async function handleCreate() {
    const trimmed = nameValue.trim();
    if (!trimmed) return;
    saving = true;
    try {
      const res = await fetch("/api/vault/lists", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: trimmed }),
      });
      if (res.ok) {
        const data = await res.json();
        oncreate(data.name, data.id);
      }
    } finally {
      saving = false;
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" && !saving) {
      handleCreate();
    }
  }
</script>

<Dialog.Root bind:open onOpenChange={(v) => { if (!v) oncancel(); }}>
  <Dialog.Content class="sm:max-w-md">
    <Dialog.Header>
      <Dialog.Title>Новый список</Dialog.Title>
      <Dialog.Description>Введите название для нового списка</Dialog.Description>
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
      <Button onclick={handleCreate} disabled={saving || !nameValue.trim()}>
        {saving ? "Создание..." : "Создать"}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
