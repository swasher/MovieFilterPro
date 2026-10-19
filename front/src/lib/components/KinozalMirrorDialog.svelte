<script lang="ts">
  import * as Dialog from "$lib/components/ui/dialog";
  import { Input } from "$lib/components/ui/input";
  import { Button } from "$lib/components/ui/button";
  import {
    MIRROR_DOMAIN_MAX_LENGTH,
    isValidMirrorDomain,
    normalizeMirrorDomain,
  } from "$lib/preferences";

  type Props = {
    open: boolean;
    existing: string[];
    onadd: (domain: string) => void;
    oncancel: () => void;
  };

  let { open = $bindable(), existing, onadd, oncancel }: Props = $props();

  let value = $state("");
  let error = $state("");

  $effect(() => {
    if (open) {
      value = "";
      error = "";
    }
  });

  const submit = () => {
    const domain = normalizeMirrorDomain(value);
    if (!domain) {
      error = "Укажите домен";
      return;
    }
    if (!isValidMirrorDomain(domain)) {
      error = `Домен должен быть вида kinozal.tv (без https://, пути и пробелов), до ${MIRROR_DOMAIN_MAX_LENGTH} символов`;
      return;
    }
    if (existing.includes(domain)) {
      error = "Такой домен уже есть";
      return;
    }
    onadd(domain);
    value = "";
  };

  const handleKeydown = (e: KeyboardEvent) => {
    if (e.key === "Enter") submit();
  };
</script>

<Dialog.Root bind:open onOpenChange={(v) => { if (!v) oncancel(); }}>
  <Dialog.Content class="sm:max-w-md">
    <Dialog.Header>
      <Dialog.Title>Добавить зеркало kinozal</Dialog.Title>
      <Dialog.Description>Введите домен, например kinozal.tv</Dialog.Description>
    </Dialog.Header>
    <div class="py-2 space-y-2">
      <Input
        bind:value
        placeholder="kinozal.tv"
        onkeydown={handleKeydown}
        autofocus
      />
      {#if error}
        <div class="text-xs text-destructive">{error}</div>
      {/if}
    </div>
    <Dialog.Footer>
      <Button variant="outline" onclick={oncancel}>Отмена</Button>
      <Button onclick={submit} disabled={!value.trim()}>Добавить</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
