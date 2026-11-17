<script lang="ts">
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import * as Dialog from "$lib/components/ui/dialog";
  import { Input } from "$lib/components/ui/input";
  import { replaceAiEndpointKey, type AiEndpoint } from "$lib/aiEndpoints";

  type Props = {
    open: boolean;
    endpoint: AiEndpoint | null;
    onsaved: () => void;
    oncancel: () => void;
  };

  let { open = $bindable(), endpoint = null, onsaved, oncancel }: Props = $props();

  let apiKeyValue = $state("");
  let saving = $state(false);
  let errorMessage = $state("");

  $effect(() => {
    if (open) {
      apiKeyValue = "";
      errorMessage = "";
      saving = false;
    }
  });

  async function handleSave(clear = false) {
    if (!endpoint) return;
    saving = true;
    errorMessage = "";
    try {
      await replaceAiEndpointKey(endpoint.id, clear ? "" : apiKeyValue.trim());
      onsaved();
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : "Не удалось сохранить ключ.";
    } finally {
      saving = false;
    }
  }
</script>

<Dialog.Root bind:open onOpenChange={(value) => { if (!value && !saving) oncancel(); }}>
  <Dialog.Content class="sm:max-w-md">
    <Dialog.Header>
      <Dialog.Title>API-ключ endpoint</Dialog.Title>
      <Dialog.Description>
        {endpoint?.name ?? ""}
        {#if endpoint?.has_api_key}
          <span class="text-muted-foreground mt-1 block text-xs">
            Текущий ключ сохранён ({endpoint.api_key_masked}). Ключ никогда не передаётся в браузер.
          </span>
        {:else}
          <span class="text-muted-foreground mt-1 block text-xs">Ключ не задан.</span>
        {/if}
      </Dialog.Description>
    </Dialog.Header>

    <div class="space-y-4 py-2">
      <Input
        bind:value={apiKeyValue}
        type="password"
        placeholder={endpoint?.has_api_key ? "Новый ключ (введите, чтобы заменить)" : "API-ключ сервера"}
      />

      {#if errorMessage}
        <div class="border-destructive/40 bg-destructive/10 text-destructive rounded-xl border px-4 py-3 text-sm">
          {errorMessage}
        </div>
      {/if}
    </div>

    <Dialog.Footer>
      {#if endpoint?.has_api_key}
        <Button
          variant="destructive-outline"
          onclick={() => handleSave(true)}
          disabled={saving}
        >
          {saving ? "Удаление..." : "Удалить ключ"}
        </Button>
      {/if}
      <Button variant="outline" onclick={() => oncancel()} disabled={saving}>Отмена</Button>
      <Button onclick={() => handleSave(false)} disabled={saving || !apiKeyValue.trim()}>
        {saving ? "Сохранение..." : "Сохранить"}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
