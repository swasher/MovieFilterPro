<script lang="ts">
  import { invalidateAll } from "$app/navigation";
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Input } from "$lib/components/ui/input";
  import { Separator } from "$lib/components/ui/separator";
  import {
    emptyPreferences,
    type PreferencesApiErrorPayload,
    type PreferencesData,
    type PreferencesUpdatePayload
  } from "$lib/preferences";

  type PreferencesFormState = {
    last_scan: string;
    scan_from_page: string;
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
    torrents_hotfolder: string;
    ignore_title: string;
    tmdb_api_key: string;
    tmdb_v4_read_access_token: string;
  };

  let { data } = $props();

  const asText = (value: string | number | null | undefined) => (value ?? "").toString();
  const asOptionalText = (value: string) => {
    const normalized = value.trim();
    return normalized ? normalized : null;
  };
  const asOptionalInteger = (value: string) => {
    const normalized = value.trim();
    return normalized ? Number.parseInt(normalized, 10) : null;
  };
  const asNumber = (value: string, fallback: number) => {
    const normalized = Number.parseFloat(value);
    return Number.isFinite(normalized) ? normalized : fallback;
  };

  const createFormState = (preferences: PreferencesData): PreferencesFormState => ({
    last_scan: preferences.last_scan ?? "",
    scan_from_page: asText(preferences.scan_from_page),
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
    kinozal_domain: preferences.kinozal_domain ?? "",
    torrents_hotfolder: preferences.torrents_hotfolder ?? "",
    ignore_title: preferences.ignore_title,
    tmdb_api_key: preferences.tmdb_api_key ?? "",
    tmdb_v4_read_access_token: preferences.tmdb_v4_read_access_token ?? ""
  });

  const buildPayload = (formState: PreferencesFormState): PreferencesUpdatePayload => ({
    last_scan: formState.last_scan.trim() || null,
    scan_from_page: asOptionalInteger(formState.scan_from_page),
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
    torrents_hotfolder: asOptionalText(formState.torrents_hotfolder),
    ignore_title: formState.ignore_title.trim(),
    tmdb_api_key: asOptionalText(formState.tmdb_api_key),
    tmdb_v4_read_access_token: asOptionalText(formState.tmdb_v4_read_access_token)
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
  let initialSnapshot = $state(payloadSnapshot(emptyFormState));

  $effect(() => {
    preferences = data.preferences ?? null;
    loadError = data.apiError ?? "";
    saveError = "";

    const nextPreferences = data.preferences ?? emptyPreferences();
    const nextFormState = createFormState(nextPreferences);
    form = nextFormState;
    hasUnsavedChanges = false;
    initialSnapshot = payloadSnapshot(nextFormState);
  });

  const currentSnapshot = $derived.by(() => {
    formRevision;
    return payloadSnapshot(form);
  });
  const isDirty = $derived(
    Boolean(preferences) && (hasUnsavedChanges || currentSnapshot !== initialSnapshot)
  );
  const savedHotfolderPath = $derived(preferences?.resolved_torrents_hotfolder ?? "");
  const hotfolderExists = $derived(preferences?.hotfolder_exists ?? false);
  const hotfolderNeedsRefresh = $derived(
    Boolean(preferences && form.torrents_hotfolder.trim() !== (preferences.torrents_hotfolder ?? ""))
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
          <CardDescription class="max-w-3xl text-sm leading-relaxed">
            Глобальные настройки Django backend теперь редактируются прямо в новом UI. Legacy-страница остаётся
            рабочей, но больше не нужна для повседневной настройки.
          </CardDescription>
        </div>

        <div class="flex flex-wrap gap-3">
          <Button variant="outline" href="http://127.0.0.1:8000/preferences/" target="_blank" rel="noreferrer">
            Django Page
          </Button>
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
            <CardDescription>Cookies, домен и hotfolder для torrent download flow.</CardDescription>
          </CardHeader>
          <CardContent class="space-y-5">
            <div class="grid gap-4 md:grid-cols-2">
              <div class="space-y-2">
                <div class="text-sm font-medium">Kinozal domain</div>
                <Input bind:value={form.kinozal_domain} placeholder="kinozal.tv" />
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium">Cookie UID</div>
                <Input bind:value={form.cookie_uid} placeholder="uid" />
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium">Cookie PASS</div>
                <Input bind:value={form.cookie_pass} type="password" placeholder="pass" />
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium">Torrents hotfolder</div>
                <Input bind:value={form.torrents_hotfolder} placeholder="/torrents_hotfolder or \\qnap\TorrentsHotFolder" />
              </div>
            </div>

            <div class="rounded-2xl border border-border/70 bg-muted/40 p-4 text-sm">
              <div class="font-medium">Hotfolder resolution</div>
              <div class="mt-2 text-muted-foreground">{preferences.hotfolder_hint}</div>
              <div class="mt-3 grid gap-2 md:grid-cols-2">
                <div>
                  <div class="text-xs uppercase tracking-[0.18em] text-muted-foreground">Resolved path</div>
                  <div class="mt-1 break-all font-mono text-xs">
                    {savedHotfolderPath || "Путь появится после сохранения."}
                  </div>
                </div>
                <div>
                  <div class="text-xs uppercase tracking-[0.18em] text-muted-foreground">Exists on backend</div>
                  <div class="mt-1">{hotfolderExists ? "Yes" : "No"}</div>
                </div>
              </div>

              {#if hotfolderNeedsRefresh}
                <div class="mt-3 text-amber-600 dark:text-amber-400">
                  Поле hotfolder изменено. Сохрани настройки, чтобы backend пересчитал resolved path.
                </div>
              {/if}
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
                <div class="text-sm font-medium">Last scan</div>
                <Input bind:value={form.last_scan} type="date" />
              </div>
              <div class="space-y-2">
                <div class="text-sm font-medium">Scan from page</div>
                <Input bind:value={form.scan_from_page} type="number" min="0" />
              </div>
            </div>

            <Separator />

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
            <div class="flex gap-3 pt-2">
              <Button variant="outline" href="/tmdb">Open TMDB</Button>
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
              <span>Hotfolder</span>
              <span>{form.torrents_hotfolder.trim() ? "Configured" : "Missing"}</span>
            </div>
            <div class="flex items-center justify-between rounded-xl border border-border/70 px-4 py-3">
              <span>TMDB read token</span>
              <span>{form.tmdb_v4_read_access_token.trim() ? "Configured" : "Missing"}</span>
            </div>
            <div class="flex items-center justify-between rounded-xl border border-border/70 px-4 py-3">
              <span>Plex token</span>
              <span>{form.plex_token.trim() ? "Configured" : "Missing"}</span>
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
