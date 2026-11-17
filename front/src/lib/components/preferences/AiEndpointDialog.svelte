<script lang="ts">
  import CheckIcon from "@lucide/svelte/icons/check";
  import ChevronsUpDownIcon from "@lucide/svelte/icons/chevrons-up-down";
  import { tick, untrack } from "svelte";
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import * as Command from "$lib/components/ui/command";
  import * as Dialog from "$lib/components/ui/dialog";
  import { Input } from "$lib/components/ui/input";
  import { Label } from "$lib/components/ui/label";
  import * as Popover from "$lib/components/ui/popover";
  import { Switch } from "$lib/components/ui/switch";
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
  // Пишется только при создании: ключ никогда не приходит с сервера.
  let apiKeyValue = $state("");
  let copySourceKey = $state(true);
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
  // Если Base URL поменяли — список нужно запросить заново.
  const aiModelsSourceKey = $derived(mode === "create" ? apiKeyValue.trim() : "");
  const modelsReady = $derived(
    aiModelsSource !== null &&
      aiModelsSource.baseUrl === baseUrlValue.trim() &&
      aiModelsSource.apiKey === aiModelsSourceKey
  );

  // При недоступном сервере моделей (fetch упал) разрешаем сохранить
  // endpoint с уже существующей конфигурацией (edit/duplicate без изменений).
  const isUnchangedExisting = $derived(
    (mode === "edit" || mode === "duplicate") &&
      endpoint !== null &&
      baseUrlValue.trim() === (endpoint.base_url ?? "").trim() &&
      modelValue.trim() === (endpoint.model ?? "").trim()
  );
  const modelIsValid = $derived(
    modelValue.trim() !== "" &&
      (modelsReady ? aiModels.includes(modelValue.trim()) : isUnchangedExisting)
  );

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
    apiKeyValue = "";
    copySourceKey = true;
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
    if (!requestedBaseUrl) {
      aiModelsError = "Сначала укажите Base URL.";
      return;
    }
    aiModelsLoading = true;
    aiModelsError = "";
    try {
      const params = new URLSearchParams();
      // Ключ сохранённого endpoint-а не должен уходить к чужому Base URL:
      // пока Base URL не менялся — просим модели по endpoint_id, сервер
      // подставит сохранённый ключ сам. Иначе шлём явный base_url и (только
      // для create) введённый ключ; пустой остаётся пустым — backend не
      // подмешивает ключ другого endpoint.
      const baseUrlChanged =
        endpoint === null || requestedBaseUrl !== (endpoint.base_url ?? "").trim();
      if (endpoint && mode !== "create" && !baseUrlChanged) {
        params.set("endpoint_id", String(endpoint.id));
      } else {
        params.set("base_url", requestedBaseUrl);
        if (mode === "create" && apiKeyValue.trim()) params.set("api_key", apiKeyValue.trim());
      }
      const res = await fetch(`/api/core/ai-models?${params.toString()}`);
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail ?? `HTTP ${res.status}`);
      aiModels = payload.models ?? [];
      aiModelsBaseUrl = payload.base_url ?? "";
      aiModelsSource = { baseUrl: requestedBaseUrl, apiKey: aiModelsSourceKey };
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
    try {
      if (isEdit && endpoint) {
        const saved = await updateAiEndpoint(endpoint.id, {
          name: trimmedName,
          base_url: trimmedBaseUrl,
          model: trimmedModel
        });
        onSaved(saved);
      } else {
        // Новый endpoint (включая дубль) сразу становится выбранным в одной
        // транзакции на сервере. Ключ дубля копируется сервером по duplicate_of
        // и на фронт не попадает.
        const saved = await createAiEndpoint({
          name: trimmedName,
          base_url: trimmedBaseUrl,
          model: trimmedModel,
          api_key: mode === "create" ? apiKeyValue.trim() : "",
          select: true,
          duplicate_of: mode === "duplicate" && copySourceKey && endpoint ? endpoint.id : undefined
        });
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

      {#if mode === "create"}
        <div class="space-y-2">
          <div class="text-sm font-medium">API key (optional)</div>
          <Input bind:value={apiKeyValue} placeholder="обычно пусто для локальных серверов" />
        </div>
      {:else if mode === "duplicate"}
        <div class="border-border/70 flex items-center justify-between rounded-xl border px-4 py-3">
          <div class="space-y-1">
            <Label for="copy-source-key" class="text-sm font-medium">Скопировать API-ключ</Label>
            <div class="text-muted-foreground text-xs">
              Ключ исходного endpoint копируется на сервере и не покидает backend.
            </div>
          </div>
          <Switch
            id="copy-source-key"
            bind:checked={copySourceKey}
            onCheckedChange={(v) => {
              copySourceKey = v;
              return v;
            }}
          />
        </div>
      {:else}
        <div class="border-border/70 rounded-xl border px-4 py-3">
          <div class="text-sm font-medium">API key</div>
          <div class="text-muted-foreground mt-1 text-xs">
            {#if endpoint?.has_api_key}
              Сохранён ({endpoint.api_key_masked}). Заменить можно кнопкой с ключом в разделе AI —
              ключ никогда не передаётся в браузер.
            {:else}
              Не задан. Добавить можно кнопкой с ключом в разделе AI.
            {/if}
          </div>
        </div>
      {/if}

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
          {#if isUnchangedExisting && !modelsReady}
            Сервер моделей недоступен — можно сохранить endpoint с текущей моделью.
          {/if}
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
