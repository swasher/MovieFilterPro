<script lang="ts">
  import { invalidateAll } from "$app/navigation";
  import { toast } from "svelte-sonner";
  import { tick } from "svelte";
  import CheckIcon from "@lucide/svelte/icons/check";
  import ChevronsUpDownIcon from "@lucide/svelte/icons/chevrons-up-down";
  import PlusIcon from "@lucide/svelte/icons/plus";
  import MinusIcon from "@lucide/svelte/icons/minus";
  import { Button } from "$lib/components/ui/button";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import * as Command from "$lib/components/ui/command";
  import { Input } from "$lib/components/ui/input";
  import * as Popover from "$lib/components/ui/popover";
  import * as Select from "$lib/components/ui/select";
  import { Separator } from "$lib/components/ui/separator";
  import { Switch } from "$lib/components/ui/switch";
  import { Label } from "$lib/components/ui/label";
  import { cn } from "$lib/utils.js";
  import {
    MAX_KINOZAL_MIRRORS,
    emptyPreferences,
    type PreferencesApiErrorPayload,
    type PreferencesData,
    type PreferencesUpdatePayload
  } from "$lib/preferences";
  import KinozalMirrorDialog from "$lib/components/KinozalMirrorDialog.svelte";

  type PreferencesFormState = {
    last_scan: string;
    scan_schedule_enabled: boolean;
    scan_interval_minutes: string;
    countries: string;
    genres: string;
    max_year: string;
    min_rating: string;
    low_countries: string;
    low_genres: string;
    low_max_year: string;
    low_min_rating: string;
    plex_address: string;
    plex_token: string;
    cookie_pass: string;
    cookie_uid: string;
    kinozal_domain: string;
    kinozal_mirrors: string[];
    qbt_url: string;
    qbt_username: string;
    qbt_password: string;
    torrents_backup_folder: string;
    ignore_title: string;
    tmdb_api_key: string;
    omdb_api_key: string;
    tavily_api_key: string;
    searxng_url: string;
    tmdb_v4_read_access_token: string;
    ai_enabled: boolean;
    ai_base_url: string;
    ai_api_key: string;
    ai_model: string;
    groq_api_key: string;
    groq_model: string;
  };

  let { data } = $props();

  // Должно совпадать с MIN_SCAN_INTERVAL_MINUTES в core/api.py.
  const MIN_SCAN_INTERVAL_MINUTES = 15;

  const asText = (value: string | number | null | undefined) => (value ?? "").toString();
  const asOptionalText = (value: string) => {
    const normalized = value.trim();
    return normalized ? normalized : null;
  };
  const asOptionalSecret = (value: string) => (value ? value : null);
  const asNumber = (value: string, fallback: number) => {
    const normalized = Number.parseFloat(value);
    return Number.isFinite(normalized) ? normalized : fallback;
  };

  const createFormState = (preferences: PreferencesData): PreferencesFormState => {
    const mirrors = preferences.kinozal_mirrors ?? [];
    const domain = preferences.kinozal_domain ?? "";
    return {
      last_scan: preferences.last_scan ?? "",
      scan_schedule_enabled: preferences.scan_interval_minutes != null,
      scan_interval_minutes: asText(preferences.scan_interval_minutes ?? MIN_SCAN_INTERVAL_MINUTES),
      countries: preferences.countries,
      genres: preferences.genres,
      max_year: asText(preferences.max_year),
      min_rating: asText(preferences.min_rating),
      low_countries: preferences.low_countries,
      low_genres: preferences.low_genres,
      low_max_year: asText(preferences.low_max_year),
      low_min_rating: asText(preferences.low_min_rating),
      plex_address: preferences.plex_address ?? "",
      plex_token: preferences.plex_token ?? "",
      cookie_pass: preferences.cookie_pass ?? "",
      cookie_uid: preferences.cookie_uid ?? "",
      // Активное зеркало всегда одно из зеркал в списке (инвариант бэкенда).
      kinozal_domain: mirrors.includes(domain) ? domain : "",
      kinozal_mirrors: mirrors,
      qbt_url: preferences.qbt_url ?? "",
      qbt_username: preferences.qbt_username ?? "",
      qbt_password: preferences.qbt_password ?? "",
      torrents_backup_folder: preferences.torrents_backup_folder ?? "",
      ignore_title: preferences.ignore_title,
      tmdb_api_key: preferences.tmdb_api_key ?? "",
      omdb_api_key: preferences.omdb_api_key ?? "",
      tavily_api_key: preferences.tavily_api_key ?? "",
      searxng_url: preferences.searxng_url ?? "",
      tmdb_v4_read_access_token: preferences.tmdb_v4_read_access_token ?? "",
      ai_enabled: preferences.ai_enabled ?? false,
      ai_base_url: preferences.ai_base_url ?? "",
      ai_api_key: preferences.ai_api_key ?? "",
      ai_model: preferences.ai_model ?? "",
      groq_api_key: preferences.groq_api_key ?? "",
      groq_model: preferences.groq_model ?? ""
    };
  };

  const buildPayload = (formState: PreferencesFormState): PreferencesUpdatePayload => ({
    last_scan: formState.last_scan.trim() || null,
    scan_interval_minutes: formState.scan_schedule_enabled
      ? Math.max(MIN_SCAN_INTERVAL_MINUTES, Number.parseInt(formState.scan_interval_minutes, 10) || MIN_SCAN_INTERVAL_MINUTES)
      : null,
    countries: formState.countries.trim(),
    genres: formState.genres.trim(),
    max_year: asNumber(formState.max_year, 1990),
    min_rating: asNumber(formState.min_rating, 3),
    low_countries: formState.low_countries.trim(),
    low_genres: formState.low_genres.trim(),
    low_max_year: asNumber(formState.low_max_year, 2000),
    low_min_rating: asNumber(formState.low_min_rating, 5),
    plex_address: asOptionalText(formState.plex_address),
    plex_token: asOptionalText(formState.plex_token),
    cookie_pass: asOptionalText(formState.cookie_pass),
    cookie_uid: asOptionalText(formState.cookie_uid),
    kinozal_domain: asOptionalText(formState.kinozal_domain),
    kinozal_mirrors: formState.kinozal_mirrors,
    qbt_url: asOptionalText(formState.qbt_url),
    qbt_username: asOptionalText(formState.qbt_username),
    qbt_password: asOptionalSecret(formState.qbt_password),
    torrents_backup_folder: asOptionalText(formState.torrents_backup_folder),
    ignore_title: formState.ignore_title.trim(),
    tmdb_api_key: asOptionalText(formState.tmdb_api_key),
    omdb_api_key: asOptionalText(formState.omdb_api_key),
    tavily_api_key: asOptionalText(formState.tavily_api_key),
    searxng_url: asOptionalText(formState.searxng_url),
    tmdb_v4_read_access_token: asOptionalText(formState.tmdb_v4_read_access_token),
    ai_enabled: formState.ai_enabled,
    ai_base_url: asOptionalText(formState.ai_base_url),
    ai_api_key: asOptionalText(formState.ai_api_key),
    ai_model: asOptionalText(formState.ai_model),
    groq_api_key: asOptionalText(formState.groq_api_key),
    groq_model: asOptionalText(formState.groq_model)
  });

  const payloadSnapshot = (formState: PreferencesFormState) => JSON.stringify(buildPayload(formState));

  const parseApiError = (payload: PreferencesApiErrorPayload | PreferencesData, fallback: string) => {
    if ("detail" in payload && payload.detail?.trim()) {
      return payload.detail.trim();
    }
    return fallback;
  };

  const emptyFormState = createFormState(emptyPreferences());

  let preferences = $state<PreferencesData | null>(null);
  let loadError = $state("");
  let saveError = $state("");
  let isSaving = $state(false);
  let form = $state<PreferencesFormState>(emptyFormState);
  let hasUnsavedChanges = $state(false);
  let formRevision = $state(0);
  let addMirrorOpen = $state(false);
  let initialSnapshot = $state(payloadSnapshot(emptyFormState));
  let qbtTestLoading = $state(false);
  let qbtTestMessage = $state("");
  let qbtTestError = $state("");

  // --- TMDB write-back status ---
  let wbEnabled = $state(true);
  let wbListsEnabled = $state(true);
  let wbTokenPresent = $state(false);
  let wbTotal = $state(0);
  let wbWithTmdb = $state(0);
  let wbLoading = $state(false);
  let wbError = $state("");

  const loadWritebackStatus = async () => {
    wbLoading = true;
    wbError = "";
    try {
      const res = await fetch("/api/vault/tmdb-writeback/status");
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.message ?? `HTTP ${res.status}`);
      wbEnabled = payload.writeback_enabled;
      wbListsEnabled = payload.lists_writeback_enabled;
      wbTokenPresent = payload.write_token_present;
      wbTotal = payload.total_user_movies;
      wbWithTmdb = payload.total_with_tmdb;
    } catch (e) {
      wbError = e instanceof Error ? e.message : String(e);
    } finally {
      wbLoading = false;
    }
  };

  const patchWriteback = async (patch: { writeback_enabled?: boolean }) => {
    // optimistic
    if (patch.writeback_enabled !== undefined) wbEnabled = patch.writeback_enabled;
    try {
      const res = await fetch("/api/vault/tmdb-writeback/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch)
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.message ?? `HTTP ${res.status}`);
      wbEnabled = payload.writeback_enabled;
      wbListsEnabled = payload.lists_writeback_enabled;
      toast.success(wbEnabled ? "TMDB write-back включён." : "TMDB write-back выключен.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
      // revert on error
      await loadWritebackStatus();
    }
  };



  // --- Local AI models ---
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
      if (form.ai_base_url.trim()) params.set("base_url", form.ai_base_url.trim());
      if (form.ai_api_key.trim()) params.set("api_key", form.ai_api_key.trim());
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
    form.ai_model = name;
    formRevision++;
    hasUnsavedChanges = true;
  };

  const closeAndFocusAiTrigger = () => {
    aiComboboxOpen = false;
    tick().then(() => {
      aiTriggerRef.focus();
    });
  };



  const markDirty = () => {
    formRevision++;
    hasUnsavedChanges = true;
  };

  const handleAddMirror = (domain: string) => {
    if (form.kinozal_mirrors.includes(domain)) return;
    form.kinozal_mirrors = [...form.kinozal_mirrors, domain];
    // Если активного зеркала нет (или оно не из списка) — активируем новое.
    if (!form.kinozal_mirrors.includes(form.kinozal_domain)) {
      form.kinozal_domain = domain;
    }
    addMirrorOpen = false;
    markDirty();
  };

  const removeSelectedMirror = () => {
    const selected = form.kinozal_domain;
    if (!selected || !form.kinozal_mirrors.includes(selected)) return;
    const index = form.kinozal_mirrors.indexOf(selected);
    const next = form.kinozal_mirrors.filter((m) => m !== selected);
    form.kinozal_mirrors = next;
    // Удаляем активное зеркало — активируем следующее за ним (иначе первое).
    const nextActive = next[index] ?? next[0] ?? "";
    form.kinozal_domain = nextActive;
    toast.success(
      nextActive
        ? `Зеркало ${selected} удалено. Активное зеркало: ${nextActive}.`
        : `Зеркало ${selected} удалено. Активных зеркал не осталось.`
    );
    markDirty();
  };

  $effect(() => {
    preferences = data.preferences ?? null;
    loadError = data.apiError ?? "";
    saveError = "";

    const nextPreferences = data.preferences ?? emptyPreferences();
    const nextFormState = createFormState(nextPreferences);
    form = nextFormState;
    hasUnsavedChanges = false;
    initialSnapshot = payloadSnapshot(nextFormState);
    void loadWritebackStatus();
  });

  const currentSnapshot = $derived.by(() => {
    formRevision;
    return payloadSnapshot(form);
  });
  const isDirty = $derived(
    Boolean(preferences) && (hasUnsavedChanges || currentSnapshot !== initialSnapshot)
  );
  const savedBackupFolderPath = $derived(preferences?.resolved_torrents_backup_folder ?? "");
  const backupFolderExists = $derived(preferences?.backup_folder_exists ?? false);
  const checkpointUrl = $derived.by(() => {
    const checkpointId = preferences?.last_scan_kinozal_id;
    const domain = preferences?.kinozal_domain;
    return checkpointId != null && domain
      ? `https://${domain}/details.php?id=${checkpointId}`
      : null;
  });
  const backupFolderNeedsRefresh = $derived(
    Boolean(preferences && form.torrents_backup_folder.trim() !== (preferences.torrents_backup_folder ?? ""))
  );

  const lastScheduledRunLabel = $derived(
    preferences?.last_scheduled_run_at
      ? new Date(preferences.last_scheduled_run_at).toLocaleString()
      : "—"
  );
  const lastScheduledStatusLabel = $derived(
    preferences?.last_scheduled_status === "success"
      ? "Успешно"
      : preferences?.last_scheduled_status === "error"
        ? "Ошибка"
        : preferences?.last_scheduled_status === "cancelled"
          ? "Отменён"
          : preferences?.last_scheduled_status ?? "—"
  );

  const resetForm = () => {
    const nextPreferences = preferences ?? emptyPreferences();
    form = createFormState(nextPreferences);
    hasUnsavedChanges = false;
    saveError = "";
  };

  const retryLoad = async () => {
    await invalidateAll();
  };

  const parseQbtTestError = (payload: unknown, fallback: string) => {
    if (!payload || typeof payload !== "object" || !("detail" in payload)) return fallback;
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail.trim();
    if (detail && typeof detail === "object") {
      const record = detail as { message?: unknown; hint?: unknown };
      if (typeof record.message === "string" && record.message.trim()) return record.message.trim();
      if (typeof record.hint === "string" && record.hint.trim()) return record.hint.trim();
    }
    return fallback;
  };

  const testQbtConnection = async () => {
    qbtTestLoading = true;
    qbtTestMessage = "";
    qbtTestError = "";

    try {
      const response = await fetch("/api/qbittorrent/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: asOptionalText(form.qbt_url),
          username: asOptionalText(form.qbt_username),
          password: asOptionalSecret(form.qbt_password)
        })
      });
      const payload = await response.json();

      if (!response.ok) {
        throw new Error(parseQbtTestError(payload, `HTTP ${response.status}`));
      }

      const version = payload.version ? `qBittorrent ${payload.version}` : "qBittorrent";
      const apiVersion = payload.web_api_version ? `, Web API ${payload.web_api_version}` : "";
      const count = payload.torrent_count ?? 0;
      qbtTestMessage = `Подключение успешно: ${version}${apiVersion}, раздач: ${count}.`;
      toast.success(qbtTestMessage);
    } catch (error) {
      qbtTestError = error instanceof Error ? error.message : "Не удалось подключиться к qBittorrent.";
      toast.error(qbtTestError);
    } finally {
      qbtTestLoading = false;
    }
  };

  const save = async () => {
    isSaving = true;
    saveError = "";

    try {
      const response = await fetch("/api/core/preferences", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(buildPayload(form))
      });

      const payload = (await response.json()) as PreferencesData | PreferencesApiErrorPayload;
      if (!response.ok) {
        throw new Error(parseApiError(payload, `HTTP ${response.status}`));
      }

      const savedPreferences = payload as PreferencesData;
      preferences = savedPreferences;
      const nextFormState = createFormState(savedPreferences);
      form = nextFormState;
      hasUnsavedChanges = false;
      initialSnapshot = payloadSnapshot(nextFormState);
      toast.success("Preferences сохранены.");
    } catch (error) {
      saveError = error instanceof Error ? error.message : "Сохранить настройки не удалось.";
      toast.error(saveError);
    } finally {
      isSaving = false;
    }
  };
</script>

{#if preferences}
  <div
    class="mx-auto flex w-full max-w-3xl flex-col gap-6 pb-8"
    oninput={() => {
      formRevision++;
      hasUnsavedChanges = true;
    }}
  >
    <Card class="border-border/70 bg-gradient-to-br from-background via-background to-muted/30">
      <CardHeader class="gap-4 md:flex-row md:items-start md:justify-between">
        <div class="space-y-2">
          <CardTitle class="text-2xl">Preferences</CardTitle>
        </div>

        <div class="flex flex-wrap gap-3">
          <Button variant="outline" onclick={resetForm} disabled={!isDirty || isSaving}>
            Reset
          </Button>
          <Button onclick={save} disabled={isSaving || !isDirty}>
            {isSaving ? "Saving..." : "Save Preferences"}
          </Button>
        </div>
      </CardHeader>
    </Card>

    {#if saveError}
      <Card class="border-destructive/40">
        <CardContent class="py-4 text-sm text-destructive">{saveError}</CardContent>
      </Card>
    {/if}

    <div class="flex flex-col gap-6">
        <Card class="border-border/70">
          <CardHeader>
            <CardTitle class="text-xl">Kinozal</CardTitle>
            <CardDescription>Cookies, зеркала Kinozal и состояние скана.</CardDescription>
          </CardHeader>
          <CardContent class="space-y-5">
            <div class="grid gap-4 md:grid-cols-2">
              <div class="space-y-2">
                <div class="text-sm font-medium">Зеркала kinozal</div>
                <div class="flex gap-2">
                  <Select.Root
                    type="single"
                    bind:value={form.kinozal_domain}
                    disabled={!form.kinozal_mirrors.length}
                    onValueChange={() => markDirty()}
                  >
                    <Select.Trigger class="flex-1" aria-label="Активное зеркало kinozal">
                      {#if form.kinozal_domain}
                        {form.kinozal_domain}
                      {:else}
                        <span class="text-muted-foreground">
                          {form.kinozal_mirrors.length ? "Выберите зеркало" : "Зеркала не заданы"}
                        </span>
                      {/if}
                    </Select.Trigger>
                    <Select.Content>
                      {#each form.kinozal_mirrors as mirror (mirror)}
                        <Select.Item value={mirror}>{mirror}</Select.Item>
                      {/each}
                    </Select.Content>
                  </Select.Root>
                  <Button
                    variant="outline"
                    size="icon"
                    onclick={() => (addMirrorOpen = true)}
                    disabled={form.kinozal_mirrors.length >= MAX_KINOZAL_MIRRORS}
                    title="Добавить зеркало"
                  >
                    <PlusIcon class="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    onclick={removeSelectedMirror}
                    disabled={!form.kinozal_mirrors.includes(form.kinozal_domain)}
                    title="Удалить выбранное зеркало"
                  >
                    <MinusIcon class="h-4 w-4" />
                  </Button>
                </div>
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium">Cookie UID</div>
                <Input bind:value={form.cookie_uid} placeholder="uid" />
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium">Cookie PASS</div>
                <Input bind:value={form.cookie_pass} type="text" placeholder="pass" />
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium">Last scan</div>
                <Input bind:value={form.last_scan} type="date" />
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium">Последняя успешно обработанная раздача (checkpoint)</div>
                <Input
                  value={preferences?.last_scan_kinozal_id?.toString() ?? "Не задан"}
                  readonly
                  aria-label="ID последней успешно обработанной раздачи"
                />
                {#if preferences?.last_scan_kinozal_id != null && checkpointUrl}
                  <a
                    href={checkpointUrl}
                    target="_blank"
                    rel="noreferrer"
                    class="text-sm text-primary underline underline-offset-4"
                  >Открыть эту раздачу на Kinozal</a>
                {:else if preferences?.last_scan_kinozal_id != null}
                  <p class="text-sm text-muted-foreground">
                    Выберите активное зеркало Kinozal, чтобы открыть эту раздачу.
                  </p>
                {:else}
                  <p class="text-sm text-muted-foreground">
                    Контрольная раздача ещё не сохранена.
                  </p>
                {/if}
              </div>
            </div>

          </CardContent>
        </Card>

        <Card class="border-border/70">
          <CardHeader>
            <CardTitle class="text-xl">qBittorrent</CardTitle>
            <CardDescription>
              Web API qBittorrent и папка backup для .torrent-файлов. URL должен быть доступен с backend.
            </CardDescription>
          </CardHeader>
          <CardContent class="space-y-5">
            <div class="grid gap-4 md:grid-cols-2">
              <div class="space-y-2">
                <div class="text-sm font-medium">Web API URL</div>
                <Input bind:value={form.qbt_url} placeholder="http://qbittorrent:8080" />
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium">Логин</div>
                <Input bind:value={form.qbt_username} placeholder="admin" autocomplete="username" />
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium">Пароль</div>
                <Input bind:value={form.qbt_password} type="password" autocomplete="current-password" />
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium">Папка backup .torrent</div>
                <Input bind:value={form.torrents_backup_folder} placeholder="/app/backup_torrents" />
              </div>
            </div>

            <div class="flex flex-wrap items-center gap-3">
              <Button variant="outline" onclick={testQbtConnection} disabled={qbtTestLoading}>
                {qbtTestLoading ? "Проверка..." : "Проверить подключение"}
              </Button>
              {#if qbtTestMessage}
                <span class="text-sm text-emerald-600 dark:text-emerald-400">{qbtTestMessage}</span>
              {/if}
              {#if qbtTestError}
                <span class="text-sm text-destructive">{qbtTestError}</span>
              {/if}
            </div>

            <div class="rounded-2xl border border-border/70 bg-muted/40 p-4 text-sm">
              <div class="font-medium">Backup folder resolution</div>
              <div class="mt-2 text-muted-foreground">{preferences.backup_folder_hint}</div>
              <div class="mt-3 grid gap-2 md:grid-cols-2">
                <div>
                  <div class="text-xs uppercase tracking-[0.18em] text-muted-foreground">Resolved path</div>
                  <div class="mt-1 break-all font-mono text-xs">
                    {savedBackupFolderPath || "Путь появится после сохранения."}
                  </div>
                </div>
                <div>
                  <div class="text-xs uppercase tracking-[0.18em] text-muted-foreground">Exists on backend</div>
                  <div class="mt-1">{backupFolderExists ? "Yes" : "No"}</div>
                </div>
              </div>

              {#if backupFolderNeedsRefresh}
                <div class="mt-3 text-amber-600 dark:text-amber-400">
                  Поле backup folder изменено. Сохрани настройки, чтобы backend пересчитал resolved path.
                </div>
              {/if}
            </div>

            <p class="text-sm text-muted-foreground">
              В Docker URL обычно выглядит как <span class="font-mono">http://qbittorrent:8080</span>,
              а папка — <span class="font-mono">/app/backup_torrents</span>. Не используй localhost:
              backend находится в отдельном контейнере.
            </p>
          </CardContent>
        </Card>

        <Card class="border-border/70">
          <CardHeader>
            <CardTitle class="text-xl">Автосканирование Kinozal</CardTitle>
            <CardDescription>Запуск сканирования по расписанию в фоновом воркере (HUEY). Требует запущенного воркера.</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="flex items-center justify-between rounded-xl border border-border/70 px-4 py-3">
              <div class="space-y-1">
                <Label for="scan-schedule-enabled" class="text-sm font-medium">Автосканирование по расписанию</Label>
                <div class="text-xs text-muted-foreground">Вкл — скан запускается автоматически с заданным интервалом. Выкл — только вручную.</div>
              </div>
              <Switch
                id="scan-schedule-enabled"
                bind:checked={form.scan_schedule_enabled}
                onCheckedChange={(v) => { form.scan_schedule_enabled = v; markDirty(); return v; }}
              />
            </div>
            <div class="space-y-2">
              <div class="text-sm font-medium">Интервал, минут</div>
              <Input
                bind:value={form.scan_interval_minutes}
                type="number"
                min={MIN_SCAN_INTERVAL_MINUTES}
                disabled={!form.scan_schedule_enabled}
              />
              <div class="text-xs text-muted-foreground">Минимум {MIN_SCAN_INTERVAL_MINUTES} минут. Интервал считается от завершения предыдущего запуска.</div>
            </div>
            <div class="rounded-xl border border-border/70 px-4 py-3 text-sm">
              <div class="flex items-center justify-between">
                <span class="text-muted-foreground">Последний плановый запуск</span>
                <span>{lastScheduledRunLabel}</span>
              </div>
              <div class="mt-1 flex items-center justify-between">
                <span class="text-muted-foreground">Статус</span>
                <span>{lastScheduledStatusLabel}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card class="border-border/70">
          <CardHeader>
            <CardTitle class="text-xl">Rules</CardTitle>
            <CardDescription>Базовые правила фильтрации и low-priority логика для скана.</CardDescription>
          </CardHeader>
          <CardContent class="space-y-5">
            <div class="grid gap-4 md:grid-cols-2">
              <div class="space-y-2">
                <div class="text-sm font-medium">Strict countries</div>
                <Input bind:value={form.countries} placeholder="СССР, Россия, Индия" />
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium">Strict genres</div>
                <Input bind:value={form.genres} placeholder="Мюзикл" />
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium">Strict max year</div>
                <Input bind:value={form.max_year} type="number" />
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium">Strict min rating</div>
                <Input bind:value={form.min_rating} type="number" min="0" max="10" step="0.1" />
              </div>
            </div>

            <Separator />

            <div class="grid gap-4 md:grid-cols-2">
              <div class="space-y-2">
                <div class="text-sm font-medium">Low countries</div>
                <Input bind:value={form.low_countries} placeholder="Таиланд, Япония, Южная Корея" />
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium">Low genres</div>
                <Input bind:value={form.low_genres} placeholder="Ужасы" />
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium">Low max year</div>
                <Input bind:value={form.low_max_year} type="number" />
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium">Low min rating</div>
                <Input bind:value={form.low_min_rating} type="number" min="0" max="10" step="0.1" />
              </div>
            </div>

            <Separator />

            <div class="space-y-2">
              <div class="text-sm font-medium">Ignore title words</div>
              <Input bind:value={form.ignore_title} placeholder="camrip, telesync, trailer" />
            </div>
          </CardContent>
        </Card>

        <Card class="border-border/70">
          <CardHeader>
            <CardTitle class="text-xl">Plex</CardTitle>
            <CardDescription>Параметры подключения для Plex-сценариев.</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="space-y-2">
              <div class="text-sm font-medium">Plex address</div>
              <Input bind:value={form.plex_address} placeholder="http://plex:32400" />
            </div>
            <div class="space-y-2">
              <div class="text-sm font-medium">Plex token</div>
              <Input bind:value={form.plex_token} placeholder="Plex token" />
            </div>
          </CardContent>
        </Card>

        <Card class="border-border/70">
          <CardHeader>
            <CardTitle class="text-xl">TMDB</CardTitle>
            <CardDescription>Ключи и токены TMDB. Authenticated token остаётся readonly.</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="space-y-2">
              <div class="text-sm font-medium">TMDB API key</div>
              <Input bind:value={form.tmdb_api_key} placeholder="TMDB API key" />
            </div>
            <div class="space-y-2">
              <div class="text-sm font-medium">TMDB v4 read access token</div>
              <Input bind:value={form.tmdb_v4_read_access_token} placeholder="TMDB read access token" />
            </div>
            <div class="space-y-2">
              <div class="text-sm font-medium">TMDB authenticated write token</div>
              <Input value={preferences.tmdb_v4_authenticated_access_token ?? ""} readonly />
            </div>
          </CardContent>
        </Card>

        <Card class="border-border/70">
          <CardHeader>
            <CardTitle class="text-xl">OMDB</CardTitle>
            <CardDescription>Ключ OMDB API для рейтингов IMDb, Rotten Tomatoes и Metacritic.</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="space-y-2">
              <div class="text-sm font-medium">OMDB API key</div>
              <Input bind:value={form.omdb_api_key} placeholder="OMDB API key" />
            </div>
          </CardContent>
        </Card>

        <Card class="border-border/70">
          <CardHeader>
            <CardTitle class="text-xl">Веб-поиск (SearXNG / Tavily)</CardTitle>
            <CardDescription>Веб-поиск для умного поиска TMDB. SearXNG URL имеет приоритет: если задан — Tavily не нужен. Без одного из них очередь TMDB sync не стартует.</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="space-y-2">
              <div class="text-sm font-medium">SearXNG URL</div>
              <Input bind:value={form.searxng_url} placeholder="http://localhost:8087/search" />
              <div class="text-xs text-muted-foreground">{form.searxng_url.trim() ? "Активный провайдер: SearXNG" : "Пусто — используется Tavily"}</div>
            </div>
            <div class="space-y-2">
              <div class="text-sm font-medium">Tavily API key</div>
              <Input bind:value={form.tavily_api_key} type="password" placeholder="tvly-..." />
            </div>
          </CardContent>
        </Card>

        <Card class="border-border/70">
          <CardHeader>
            <CardTitle class="text-xl">Local AI</CardTitle>
            <CardDescription>OpenAI-совместимый локальный сервер (Ollama / LM Studio / Lemonade / Unsloth) для будущих фич. Пока только храним настройки, ничего их не вызывает.</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="flex items-center justify-between rounded-xl border border-border/70 px-4 py-3">
              <div class="space-y-1">
                <Label for="ai-enabled" class="text-sm font-medium">Local AI enabled</Label>
                <div class="text-xs text-muted-foreground">Вкл — будущие фичи смогут обращаться к локальному AI. Выкл — всё без AI.</div>
              </div>
              <Switch id="ai-enabled" bind:checked={form.ai_enabled} onCheckedChange={(v) => { form.ai_enabled = v; formRevision++; hasUnsavedChanges = true; return v; }} />
            </div>
            <div class="space-y-2">
              <div class="text-sm font-medium">Base URL</div>
              <Input bind:value={form.ai_base_url} placeholder="http://localhost:11434/v1" />
              <div class="text-xs text-muted-foreground">Без слэша в конце. Lemonade обычно http://localhost:13305/v1, Unsloth — http://localhost:8888/v1.</div>
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
                        <span class="truncate">{form.ai_model.trim() || "Select model..."}</span>
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
                                class={cn(form.ai_model.trim() !== modelName && "text-transparent")}
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
                <div class="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">{aiModelsError}</div>
              {/if}
            </div>
            <div class="space-y-2">
              <div class="text-sm font-medium">API key (optional)</div>
              <Input bind:value={form.ai_api_key} type="password" placeholder="обычно пусто для локальных серверов" />
            </div>
          </CardContent>
        </Card>

        <Card class="border-border/70">
          <CardHeader>
            <CardTitle class="text-xl">Groq</CardTitle>
            <CardDescription>Облачный Groq API для LLM-фич (рекомендации, анализ).</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="space-y-2">
              <div class="text-sm font-medium">Groq API key</div>
              <Input bind:value={form.groq_api_key} type="password" placeholder="gsk_..." />
            </div>
            <div class="space-y-2">
              <div class="text-sm font-medium">Groq model</div>
              <Input bind:value={form.groq_model} placeholder="llama-3.3-70b-versatile" />
            </div>
          </CardContent>
        </Card>

        <Card class="border-border/70">
          <CardHeader>
            <CardTitle class="text-xl">TMDB Write-back</CardTitle>
            <CardDescription>Обратная синхронизация Vault → TMDB (watchlist/favorite/rating). Работает через tmdb_adapter.</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4 text-sm">
            {#if wbError}
              <div class="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-destructive">{wbError}</div>
            {/if}
            <div class="flex items-center justify-between rounded-xl border border-border/70 px-4 py-3">
              <div class="space-y-1">
                <Label for="wb-enabled" class="text-sm font-medium">TMDB Write-back</Label>
                <div class="text-xs text-muted-foreground">Вкл — статусы, оценки и списки уходят в TMDB (создаются на лету). Выкл — всё локально.</div>
              </div>
              <Switch id="wb-enabled" bind:checked={wbEnabled} onCheckedChange={(v) => { patchWriteback({ writeback_enabled: v }); return v; }} />
            </div>
            <div class="flex gap-3 pt-1">
              <Button variant="outline" href="/tmdb-auth">TMDB Auth</Button>
              <Button variant="outline" href="/tmdb-writeback">TMDB Write-back Error Log →</Button>
            </div>
          </CardContent>
        </Card>

        <Card class="border-border/70">
          <CardHeader>
            <CardTitle class="text-xl">Status</CardTitle>
            <CardDescription>Быстрые сигналы по текущему состоянию настроек.</CardDescription>
          </CardHeader>
          <CardContent class="space-y-3 text-sm">
            <div class="flex items-center justify-between rounded-xl border border-border/70 px-4 py-3">
              <span>Kinozal auth</span>
              <span>{form.cookie_uid.trim() && form.cookie_pass.trim() ? "Configured" : "Missing"}</span>
            </div>
            <div class="flex items-center justify-between rounded-xl border border-border/70 px-4 py-3">
              <span>Зеркала kinozal</span>
              <span>{form.kinozal_mirrors.length} шт.{form.kinozal_domain ? ` / активно: ${form.kinozal_domain}` : ""}</span>
            </div>
            <div class="flex items-center justify-between rounded-xl border border-border/70 px-4 py-3">
              <span>qBittorrent</span>
              <span>{form.qbt_url.trim() ? "Configured" : "Missing"}</span>
            </div>
            <div class="flex items-center justify-between rounded-xl border border-border/70 px-4 py-3">
              <span>Torrent backup folder</span>
              <span>{form.torrents_backup_folder.trim() ? "Configured" : "Missing"}</span>
            </div>
            <div class="flex items-center justify-between rounded-xl border border-border/70 px-4 py-3">
              <span>TMDB read token</span>
              <span>{form.tmdb_v4_read_access_token.trim() ? "Configured" : "Missing"}</span>
            </div>
            <div class="flex items-center justify-between rounded-xl border border-border/70 px-4 py-3">
              <span>OMDB API key</span>
              <span>{form.omdb_api_key.trim() ? "Configured" : "Missing"}</span>
            </div>
            <div class="flex items-center justify-between rounded-xl border border-border/70 px-4 py-3">
              <span>Веб-поиск</span>
              <span>{form.searxng_url.trim() ? "SearXNG" : form.tavily_api_key.trim() ? "Tavily" : "Missing"}</span>
            </div>
            <div class="flex items-center justify-between rounded-xl border border-border/70 px-4 py-3">
              <span>Plex token</span>
              <span>{form.plex_token.trim() ? "Configured" : "Missing"}</span>
            </div>
            <div class="flex items-center justify-between rounded-xl border border-border/70 px-4 py-3">
              <span>Local AI</span>
              <span>{form.ai_enabled && form.ai_base_url.trim() && form.ai_model.trim() ? "Configured" : form.ai_enabled ? "Incomplete" : "Disabled"}</span>
            </div>
            <div class="flex items-center justify-between rounded-xl border border-border/70 px-4 py-3">
              <span>Groq</span>
              <span>{form.groq_api_key.trim() && form.groq_model.trim() ? "Configured" : form.groq_api_key.trim() || form.groq_model.trim() ? "Incomplete" : "Missing"}</span>
            </div>
          </CardContent>
        </Card>
    </div>

    <div class="flex flex-wrap gap-3">
      <Button variant="outline" onclick={resetForm} disabled={!isDirty || isSaving}>
        Reset
      </Button>
      <Button onclick={save} disabled={isSaving || !isDirty}>
        {isSaving ? "Saving..." : "Save Preferences"}
      </Button>
    </div>

    <KinozalMirrorDialog
      bind:open={addMirrorOpen}
      existing={form.kinozal_mirrors}
      onadd={handleAddMirror}
      oncancel={() => (addMirrorOpen = false)}
    />
  </div>
{:else}
  <div class="mx-auto flex w-full max-w-3xl flex-col gap-6">
    <Card class="border-destructive/40">
      <CardHeader>
        <CardTitle>Не удалось загрузить Preferences</CardTitle>
        <CardDescription>{loadError || "Unknown API error"}</CardDescription>
      </CardHeader>
      <CardContent class="flex flex-wrap gap-3">
        <Button onclick={retryLoad}>Retry</Button>
        <Button variant="outline" href="http://127.0.0.1:8000/preferences/" target="_blank" rel="noreferrer">
          Open Django Page
        </Button>
      </CardContent>
    </Card>
  </div>
{/if}
