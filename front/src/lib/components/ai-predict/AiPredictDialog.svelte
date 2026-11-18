<script lang="ts">
  import { Loader, Sparkles } from "@lucide/svelte";
  import * as Dialog from "$lib/components/ui/dialog";
  import { Badge } from "$lib/components/ui/badge";
  import { Button } from "$lib/components/ui/button";
  import * as Select from "$lib/components/ui/select";
  import {
    fetchLastKinozalPrediction,
    fetchLastPrediction,
    getPreferredTasteId,
    listTasteProfiles,
    predictionScoreLabel,
    resolveTasteProfile,
    runKinozalPrediction,
    runPrediction,
    setPreferredTasteId,
    type AiPrediction,
    type PredictionSource,
    type TasteProfile
  } from "$lib/aiPredict";

  type Props = {
    open: boolean;
    movieId: number;
    movieTitle: string;
    source?: PredictionSource;
  };

  let { open = $bindable(), movieId, movieTitle, source = "vault" }: Props = $props();

  let profiles = $state<TasteProfile[]>([]);
  let profilesLoading = $state(false);
  let profilesError = $state("");
  let selectedId = $state("");
  let prediction = $state<AiPrediction | null>(null);
  let lastLoading = $state(false);
  let running = $state(false);
  let runError = $state("");

  let preparedKey = "";

  const selectedProfile = $derived(
    profiles.find((profile) => String(profile.id) === selectedId) ?? null
  );

  const durationLabel = $derived(
    prediction?.duration_ms != null ? `${(prediction.duration_ms / 1000).toFixed(1)} с` : null
  );

  $effect(() => {
    const key = `${open}:${source}:${movieId}`;
    if (!open) {
      preparedKey = "";
      return;
    }
    if (key === preparedKey) {
      return;
    }
    preparedKey = key;
    void prepare();
  });

  async function prepare() {
    runError = "";
    prediction = null;

    if (!profiles.length) {
      profilesLoading = true;
      profilesError = "";
      try {
        profiles = await listTasteProfiles();
      } catch (error) {
        profilesError = error instanceof Error ? error.message : "Не удалось загрузить профили.";
      } finally {
        profilesLoading = false;
      }
    }

    const resolved = resolveTasteProfile(profiles, getPreferredTasteId());
    selectedId = resolved ? String(resolved.id) : "";
    await loadLastPrediction();
  }

  async function loadLastPrediction() {
    prediction = null;
    if (!movieId || !selectedProfile) {
      return;
    }
    lastLoading = true;
    try {
      prediction =
        source === "kinozal"
          ? await fetchLastKinozalPrediction(movieId, selectedProfile.id)
          : await fetchLastPrediction(movieId, selectedProfile.id);
    } catch {
      // отсутствие истории — не ошибка
    } finally {
      lastLoading = false;
    }
  }

  function handleProfileChange(value: string) {
    selectedId = value;
    const parsed = Number.parseInt(value, 10);
    setPreferredTasteId(Number.isFinite(parsed) ? parsed : null);
    void loadLastPrediction();
  }

  async function handleRun() {
    if (!movieId) {
      return;
    }
    running = true;
    runError = "";
    try {
      prediction =
        source === "kinozal"
          ? await runKinozalPrediction(movieId, selectedProfile?.id ?? null)
          : await runPrediction(movieId, selectedProfile?.id ?? null);
      if (prediction.taste_profile_id !== null) {
        setPreferredTasteId(prediction.taste_profile_id);
      }
    } catch (error) {
      runError = error instanceof Error ? error.message : "Не удалось выполнить предсказание.";
    } finally {
      running = false;
    }
  }
</script>

<Dialog.Root bind:open>
  <Dialog.Content class="sm:max-w-2xl max-h-[calc(100dvh-2rem)] grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden">
    <Dialog.Header>
      <Dialog.Title class="flex items-center gap-2">
        <Sparkles class="size-4" />
        AI predict
      </Dialog.Title>
      <Dialog.Description>{movieTitle}</Dialog.Description>
    </Dialog.Header>

    <div class="min-h-0 space-y-4 overflow-y-auto py-2">
      {#if profilesError}
        <div class="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {profilesError}
        </div>
      {/if}

      {#if profilesLoading}
        <div class="text-muted-foreground text-sm">Загрузка профилей вкусов…</div>
      {:else if !profiles.length}
        <div class="space-y-3 rounded-xl border border-border/70 px-4 py-4 text-sm">
          <div>Профилей вкусов пока нет. Добавьте хотя бы один в Preferences → Taste.</div>
          <Button variant="outline" size="sm" href="/preferences">Открыть Preferences</Button>
        </div>
      {:else}
        <div class="space-y-2">
          <div class="text-sm font-medium">Профиль вкусов</div>
          <div class="flex gap-2">
            <Select.Root type="single" value={selectedId} onValueChange={handleProfileChange}>
              <Select.Trigger class="flex-1" aria-label="Профиль вкусов для предсказания">
                {selectedProfile?.name ?? "Выберите профиль"}
              </Select.Trigger>
              <Select.Content>
                {#each profiles as profile (profile.id)}
                  <Select.Item value={String(profile.id)}>{profile.name}</Select.Item>
                {/each}
              </Select.Content>
            </Select.Root>
            <Button onclick={handleRun} disabled={running}>
              {#if running}
                <Loader class="size-4 animate-spin" />
                Считаю…
              {:else}
                Запустить анализ
              {/if}
            </Button>
          </div>
        </div>

        {#if runError}
          <div class="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {runError}
          </div>
        {/if}

        {#if lastLoading}
          <div class="text-muted-foreground text-sm">Загрузка последнего результата…</div>
        {:else if prediction}
          <div class="space-y-3">
            <div class="flex flex-wrap items-center gap-2">
              <Badge variant={prediction.status === "error" ? "destructive" : "secondary"}>
                {prediction.status_display}
              </Badge>
              {#if prediction.score !== null}
                <Badge variant="outline">{predictionScoreLabel(prediction)}</Badge>
              {/if}
              {#if prediction.verdict_display}
                <Badge variant="outline">{prediction.verdict_display}</Badge>
              {/if}
              {#if durationLabel}
                <span class="text-muted-foreground text-xs">{durationLabel}</span>
              {/if}
              {#if prediction.model_name}
                <span class="text-muted-foreground truncate text-xs">{prediction.model_name}</span>
              {/if}
            </div>

            {#if prediction.status === "error" && prediction.error}
              <div class="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {prediction.error}
              </div>
            {/if}

            {#if prediction.result_text}
              <div class="max-h-[420px] overflow-auto rounded-xl border border-border/70 bg-muted/30 px-4 py-3">
                <pre class="font-sans text-sm whitespace-pre-wrap">{prediction.result_text}</pre>
              </div>
            {/if}
          </div>
        {:else}
          <div class="text-muted-foreground text-sm">
            {#if running}
              Идёт прогон…
            {:else}
              Для этого фильма и профиля прогонов ещё не было.
            {/if}
          </div>
        {/if}
      {/if}
    </div>

    <Dialog.Footer>
      <Button variant="outline" onclick={() => (open = false)}>Закрыть</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
