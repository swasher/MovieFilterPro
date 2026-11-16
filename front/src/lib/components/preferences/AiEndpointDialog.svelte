<script lang="ts">
  import CheckIcon from "@lucide/svelte/icons/check";
  import ChevronsUpDownIcon from "@lucide/svelte/icons/chevrons-up-down";
  import { tick, untrack } from "svelte";
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import * as Command from "$lib/components/ui/command";
  import * as Dialog from "$lib/components/ui/dialog";
  import { Input } from "$lib/components/ui/input";
  import * as Popover from "$lib/components/ui/popover";
  import { cn } from "$lib/utils.js";
  import {
    createAiEndpoint,
    updateAiEndpoint,
    type AiEndpoint
  } from "$lib/aiEndpoints";

  type Mode = "create" | "edit" | "duplicate";

  type Props = {
    open: boolean;
    mode?: Mode;
    /** Источник для edit/duplicate. Для create — null. */
    endpoint?: AiEndpoint | null;
    /** Подсказанное имя для duplicate (уже уникальное). */
    suggestedName?: string;
    onSaved: (endpoint: AiEndpoint) => void;
    onCancel: () => void;
  };

  let {
    open = $bindable(),
    mode = "create",
    endpoint = null,
    suggestedName = "",
    onSaved,
    onCancel
  }: Props = $props();

  let nameValue = $state("");
  let baseUrlValue = $state("");
  let modelValue = $state("");
  let apiKeyValue = $state("");
  let errorMessage = $state("");
  let saving = $state(false);

  let aiModels = $state<string[]>([]);
  let aiModelsLoading = $state(false);
  let aiModelsError = $state("");
  let aiModelsBaseUrl = $state("");
  let aiModelsSource = $state<{ baseUrl: string; apiKey: string } | null>(null);
  let aiComboboxOpen = $state(false);
  let aiTriggerRef = $state<HTMLButtonElement>(null!);

  const isEdit = $derived(mode === "edit");

  // Список моделей относится к конкретной паре Base URL + API key.
  // Если поля поменяли — список нужно запросить заново.
  const modelsReady = $derived(
    aiModelsSource !== null &&
      aiModelsSource.baseUrl === baseUrlValue.trim() &&
      aiModelsSource.apiKey === apiKeyValue.trim()
  );
  const modelIsValid = $derived(modelsReady && aiModels.includes(modelValue.trim()));

  const title = $derived(
    mode === "edit"
      ? "Редактирование AI endpoint"
      : mode === "duplicate"
        ? "Дублирование AI endpoint"
        : "Новый AI endpoint"
  );

  $effect(() => {
    if (!open) return;

    const initialBaseUrl = endpoint?.base_url ?? "";
    nameValue =
      mode === "duplicate"
        ? suggestedName || `${endpoint?.name ?? ""} copy`
        : (endpoint?.name ?? "");
    baseUrlValue = initialBaseUrl;
    modelValue = endpoint?.model ?? "";
    apiKeyValue = endpoint?.api_key ?? "";
    errorMessage = "";
    aiModels = [];
    aiModelsError = "";
    aiModelsBaseUrl = "";
    aiModelsSource = null;
    aiComboboxOpen = false;
    saving = false;

    // При редактировании/дублировании список моделей уже можно запросить.
    if (initialBaseUrl.trim()) {
      untrack(() => {
        void loadAiModels(false);
      });
    }
  });

  const loadAiModels = async (notify = true) => {
    const requestedBaseUrl = baseUrlValue.trim();
    const requestedApiKey = apiKeyValue.trim();
    if (!requestedBaseUrl) {
      aiModelsError = "Сначала укажите Base URL.";
      return;
    }
    aiModelsLoading = true;
    aiModelsError = "";
    try {
      const params = new URLSearchParams();
      params.set("base_url", requestedBaseUrl);
      if (requestedApiKey) params.set("api_key", requestedApiKey);
      const res = await fetch(`/api/core/ai-models?${params.toString()}`);
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail ?? `HTTP ${res.status}`);
      aiModels = payload.models ?? [];
      aiModelsBaseUrl = payload.base_url ?? "";
      aiModelsSource = { baseUrl: requestedBaseUrl, apiKey: requestedApiKey };
      if (!aiModels.length) {
        aiModelsError = "Сервер ответил, но список моделей пуст.";
      } else {
        // Модель, которой больше нет в списке, выбираем заново.
        if (modelValue && !aiModels.includes(modelValue)) {
          modelValue = "";
        }
        if (notify) toast.success(`Найдено моделей: ${aiModels.length}`);
      }
    } catch (e) {
      aiModels = [];
      aiModelsSource = null;
      aiModelsError = e instanceof Error ? e.message : String(e);
      if (notify) toast.error(aiModelsError);
    } finally {
      aiModelsLoading = false;
    }
  };

  const pickAiModel = (name: string) => {
    modelValue = name;
  };

  const closeAndFocusAiTrigger = () => {
    aiComboboxOpen = false;
    tick().then(() => {
      aiTriggerRef.focus();
    });
  };

  async function handleSave() {
    const trimmedName = nameValue.trim();
    const trimmedBaseUrl = baseUrlValue.trim();
    const trimmedModel = modelValue.trim();
    if (!trimmedName) {
      errorMessage = "Название endpoint не может быть пустым.";
      return;
    }
    if (!trimmedBaseUrl) {
      errorMessage = "Base URL не может быть пустым.";
      return;
    }
    if (!modelIsValid) {
      errorMessage = "Выберите модель из списка — нажмите Get models.";
      return;
    }

    saving = true;
    errorMessage = "";
    const payload = {
      name: trimmedName,
      base_url: trimmedBaseUrl,
      model: trimmedModel,
      api_key: apiKeyValue.trim()
    };
    try {
      if (isEdit && endpoint) {
        const saved = await updateAiEndpoint(endpoint.id, payload);
        onSaved(saved);
      } else {
        const saved = await createAiEndpoint(payload);
        onSaved(saved);
      }
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : "Не удалось сохранить endpoint.";
    } finally {
      saving = false;
    }
  }
</script>

<Dialog.Root bind:open onOpenChange={(value) => { if (!value) onCancel(); }}>
  <Dialog.Content
    class="sm:max-w-xl max-h-[calc(100dvh-2rem)] grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden"
    interactOutsideBehavior="ignore"
    escapeKeydownBehavior="ignore"
  >
    <Dialog.Header>
      <Dialog.Title>{title}</Dialog.Title>
    </Dialog.Header>

    <div class="min-h-0 space-y-4 overflow-y-auto py-2">
      <div class="space-y-2">
        <div class="text-sm font-medium">Название</div>
        <Input bind:value={nameValue} placeholder="Например, Ollama local" autofocus />
      </div>

      <div class="space-y-2">
        <div class="text-sm font-medium">Base URL</div>
        <Input bind:value={baseUrlValue} placeholder="http://localhost:11434/v1" />
        <div class="text-muted-foreground text-xs">
          Без слэша в конце. Lemonade обычно http://localhost:13305/v1, Unsloth — http://localhost:8888/v1,
          Groq — https://api.groq.com/openai/v1.
        </div>
      </div>

      <div class="space-y-2">
        <div class="text-sm font-medium">API key (optional)</div>
        <Input bind:value={apiKeyValue} placeholder="обычно пусто для локальных серверов" />
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
                  disabled={!modelsReady || !aiModels.length}
                >
                  <span class="truncate">
                    {modelValue.trim() || (modelsReady ? "Select model..." : "Сначала Get models")}
                  </span>
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
                        <CheckIcon class={cn(modelValue.trim() !== modelName && "text-transparent")} />
                        <span class="truncate">{modelName}</span>
                      </Command.Item>
                    {/each}
                  </Command.Group>
                </Command.List>
              </Command.Root>
            </Popover.Content>
          </Popover.Root>
          <Button
            variant="outline"
            onclick={() => loadAiModels()}
            disabled={aiModelsLoading || !baseUrlValue.trim()}
          >
            {aiModelsLoading ? "Loading..." : "Get models"}
          </Button>
        </div>
        <div class="text-muted-foreground text-xs">
          Модель выбирается из списка, который вернул сервер по Base URL и API-ключу.
        </div>
        {#if aiModelsError}
          <div class="border-destructive/40 bg-destructive/10 text-destructive rounded-xl border px-4 py-3 text-sm">
            {aiModelsError}
          </div>
        {/if}
      </div>

      {#if errorMessage}
        <div class="border-destructive/40 bg-destructive/10 text-destructive rounded-xl border px-4 py-3 text-sm">
          {errorMessage}
        </div>
      {/if}
    </div>

    <Dialog.Footer>
      <Button variant="outline" onclick={() => onCancel()} disabled={saving}>Отмена</Button>
      <Button onclick={handleSave} disabled={saving || !nameValue.trim() || !modelIsValid}>
        {saving ? "Сохранение..." : "Сохранить"}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
