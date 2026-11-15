<script lang="ts">
  import CheckIcon from "@lucide/svelte/icons/check";
  import ChevronsUpDownIcon from "@lucide/svelte/icons/chevrons-up-down";
  import { tick } from "svelte";
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import * as Command from "$lib/components/ui/command";
  import { Input } from "$lib/components/ui/input";
  import { Label } from "$lib/components/ui/label";
  import * as Popover from "$lib/components/ui/popover";
  import { Switch } from "$lib/components/ui/switch";
  import { cn } from "$lib/utils.js";
  import { getPreferencesStore } from "./store.svelte.js";

  const store = getPreferencesStore();

  let aiModels = $state<string[]>([]);
  let aiModelsLoading = $state(false);
  let aiModelsError = $state("");
  let aiModelsBaseUrl = $state("");
  let aiComboboxOpen = $state(false);
  let aiTriggerRef = $state<HTMLButtonElement>(null!);

  const loadAiModels = async () => {
    aiModelsLoading = true;
    aiModelsError = "";
    try {
      const params = new URLSearchParams();
      if (store.form.ai_base_url.trim()) params.set("base_url", store.form.ai_base_url.trim());
      if (store.form.ai_api_key.trim()) params.set("api_key", store.form.ai_api_key.trim());
      const qs = params.toString() ? `?${params.toString()}` : "";
      const res = await fetch(`/api/core/ai-models${qs}`);
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail ?? `HTTP ${res.status}`);
      aiModels = payload.models ?? [];
      aiModelsBaseUrl = payload.base_url ?? "";
      if (!aiModels.length) {
        aiModelsError = "Сервер ответил, но список моделей пуст.";
      } else {
        toast.success(`Найдено моделей: ${aiModels.length}`);
      }
    } catch (e) {
      aiModels = [];
      aiModelsError = e instanceof Error ? e.message : String(e);
      toast.error(aiModelsError);
    } finally {
      aiModelsLoading = false;
    }
  };

  const pickAiModel = (name: string) => {
    store.form.ai_model = name;
    store.markDirty();
  };

  const closeAndFocusAiTrigger = () => {
    aiComboboxOpen = false;
    tick().then(() => {
      aiTriggerRef.focus();
    });
  };
</script>

<div class="space-y-4">
  <div class="border-border/70 flex items-center justify-between rounded-xl border px-4 py-3">
    <div class="space-y-1">
      <Label for="ai-enabled" class="text-sm font-medium">Local AI enabled</Label>
      <div class="text-muted-foreground text-xs">
        Вкл — будущие фичи смогут обращаться к локальному AI. Выкл — всё без AI.
      </div>
    </div>
    <Switch
      id="ai-enabled"
      bind:checked={store.form.ai_enabled}
      onCheckedChange={(v) => {
        store.form.ai_enabled = v;
        store.markDirty();
        return v;
      }}
    />
  </div>

  <div class="space-y-2">
    <div class="text-sm font-medium">Base URL</div>
    <Input bind:value={store.form.ai_base_url} placeholder="http://localhost:11434/v1" />
    <div class="text-muted-foreground text-xs">
      Без слэша в конце. Lemonade обычно http://localhost:13305/v1, Unsloth — http://localhost:8888/v1.
    </div>
  </div>

  <div class="space-y-2">
    <div class="text-sm font-medium">Model</div>
    <div class="flex gap-2">
      <Popover.Root bind:open={aiComboboxOpen}>
        <Popover.Trigger bind:ref={aiTriggerRef}>
          {#snippet child({ props })}
            <Button
              {...props}
              variant="outline"
              role="combobox"
              aria-expanded={aiComboboxOpen}
              class="flex-1 justify-between"
            >
              <span class="truncate">{store.form.ai_model.trim() || "Select model..."}</span>
              <ChevronsUpDownIcon data-icon="inline-end" class="opacity-50" />
            </Button>
          {/snippet}
        </Popover.Trigger>
        <Popover.Content class="w-[320px] p-0" align="start">
          <Command.Root>
            <Command.Input placeholder="Search model..." />
            <Command.List>
              <Command.Empty>
                {aiModels.length ? "No model found." : "No models loaded. Click Get models."}
              </Command.Empty>
              <Command.Group value="ai-models" heading={aiModelsBaseUrl || undefined}>
                {#each aiModels as modelName (modelName)}
                  <Command.Item
                    value={modelName}
                    onSelect={() => {
                      pickAiModel(modelName);
                      closeAndFocusAiTrigger();
                    }}
                  >
                    <CheckIcon
                      class={cn(store.form.ai_model.trim() !== modelName && "text-transparent")}
                    />
                    <span class="truncate">{modelName}</span>
                  </Command.Item>
                {/each}
              </Command.Group>
            </Command.List>
          </Command.Root>
        </Popover.Content>
      </Popover.Root>
      <Button variant="outline" onclick={loadAiModels} disabled={aiModelsLoading}>
        {aiModelsLoading ? "Loading..." : "Get models"}
      </Button>
    </div>
    {#if aiModelsError}
      <div class="border-destructive/40 bg-destructive/10 text-destructive rounded-xl border px-4 py-3 text-sm">
        {aiModelsError}
      </div>
    {/if}
  </div>

  <div class="space-y-2">
    <div class="text-sm font-medium">API key (optional)</div>
    <Input
      bind:value={store.form.ai_api_key}
      type="password"
      placeholder="обычно пусто для локальных серверов"
    />
  </div>
</div>
