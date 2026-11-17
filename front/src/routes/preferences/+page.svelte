<script lang="ts">
  import { invalidateAll, replaceState } from "$app/navigation";
  import { page } from "$app/state";
  import MenuIcon from "@lucide/svelte/icons/menu";
  import PasswordChangeForm from "$lib/components/PasswordChangeForm.svelte";
  import DiagnosticsSection from "$lib/components/preferences/DiagnosticsSection.svelte";
  import ImagesSection from "$lib/components/preferences/ImagesSection.svelte";
  import KinozalSection from "$lib/components/preferences/KinozalSection.svelte";
  import KinoriumSyncSection from "$lib/components/preferences/KinoriumSyncSection.svelte";
  import LocalAiSection from "$lib/components/preferences/LocalAiSection.svelte";
  import OmdbSection from "$lib/components/preferences/OmdbSection.svelte";
  import PlexSection from "$lib/components/preferences/PlexSection.svelte";
  import PreferencesNav from "$lib/components/preferences/PreferencesNav.svelte";
  import QbittorrentSection from "$lib/components/preferences/QbittorrentSection.svelte";
  import RulesSection from "$lib/components/preferences/RulesSection.svelte";
  import TasteSection from "$lib/components/preferences/TasteSection.svelte";
  import TmdbSection from "$lib/components/preferences/TmdbSection.svelte";
  import TmdbWritebackSection from "$lib/components/preferences/TmdbWritebackSection.svelte";
  import WebSearchSection from "$lib/components/preferences/WebSearchSection.svelte";
  import { PreferencesStore, setPreferencesStore } from "$lib/components/preferences/store.svelte.js";
  import {
    PREFERENCES_SECTIONS,
    dirtySections,
    resolveSectionId,
    type PreferencesSectionId
  } from "$lib/components/preferences/types.js";
  import { Button } from "$lib/components/ui/button";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import * as Sheet from "$lib/components/ui/sheet";

  let { data } = $props();

  const store = new PreferencesStore(() => data);
  setPreferencesStore(store);

  let aiEndpoints = $state(data.endpoints ?? []);

  // Раздел живёт в URL (?section=…), чтобы пережить перезагрузку и работать как deep-link.
  const resolveInitialSection = (): PreferencesSectionId =>
    resolveSectionId(page.url.searchParams.get("section")) ?? "kinozal";

  let activeSection = $state<PreferencesSectionId>(resolveInitialSection());
  let navOpen = $state(false);

  const activeSectionMeta = $derived(
    PREFERENCES_SECTIONS.find((item) => item.id === activeSection) ?? PREFERENCES_SECTIONS[0]
  );

  const dirty = $derived(dirtySections(store.form, store.initialSnapshot));
  const dirtyTotal = $derived([...dirty.values()].reduce((sum, count) => sum + count, 0));
  const dirtySectionTitles = $derived(
    PREFERENCES_SECTIONS.filter((item) => dirty.has(item.id)).map((item) => item.title)
  );

  // Разделы, где не заданы обязательные для работы значения — красная точка в навигации.
  const missingSections = $derived.by<PreferencesSectionId[]>(() => {
    const form = store.form;
    const result: PreferencesSectionId[] = [];
    if (!(form.cookie_uid.trim() && form.cookie_pass.trim() && form.kinozal_mirrors.length)) {
      result.push("kinozal");
    }
    if (!form.qbt_url.trim()) result.push("qbittorrent");
    if (!(form.tmdb_v4_read_access_token.trim() || form.tmdb_api_key.trim())) {
      result.push("tmdb");
    }
    return result;
  });

  const selectSection = (id: PreferencesSectionId) => {
    activeSection = id;
    navOpen = false;
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    url.searchParams.set("section", id);
    // replaceState обновляет URL без повторного load() — несохранённые изменения не теряются.
    void replaceState(url, page.state);
  };

  const retryLoad = async () => {
    await invalidateAll();
  };

  $effect(() => {
    store.applyData({ preferences: data.preferences, apiError: data.apiError });
  });
</script>

{#if store.preferences}
  <div class="mx-auto flex w-full max-w-6xl flex-col gap-6 px-3 pt-4 pb-8 md:px-4">
    <div class="flex items-center justify-between gap-3">
      <h1 class="text-2xl font-semibold tracking-tight">Preferences</h1>
      <Button variant="outline" size="sm" class="lg:hidden" onclick={() => (navOpen = true)}>
        <MenuIcon class="size-4" />
        Разделы
      </Button>
    </div>

    {#if store.saveError}
      <Card class="border-destructive/40">
        <CardContent class="text-destructive py-4 text-sm">{store.saveError}</CardContent>
      </Card>
    {/if}

    <div class="grid gap-6 lg:grid-cols-[210px_minmax(0,1fr)]">
      <aside class="hidden lg:block">
        <div class="sticky top-16 max-h-[calc(100svh-5rem)] overflow-y-auto">
          <PreferencesNav
            sections={PREFERENCES_SECTIONS}
            active={activeSection}
            dirtyCounts={dirty}
            missing={missingSections}
            onselect={selectSection}
          />
        </div>
      </aside>

      <div class="flex min-w-0 flex-col gap-4">
        {#if activeSection === "account"}
          <PasswordChangeForm />
        {:else}
          <Card class="border-border/70">
            <CardHeader>
              <CardTitle class="text-xl">{activeSectionMeta.title}</CardTitle>
              <CardDescription>{activeSectionMeta.description}</CardDescription>
            </CardHeader>
            <CardContent
              class="space-y-5"
              oninput={() => store.markDirty()}
            >
              {#if activeSection === "kinozal"}
                <KinozalSection />
              {:else if activeSection === "rules"}
                <RulesSection />
              {:else if activeSection === "qbittorrent"}
                <QbittorrentSection />
              {:else if activeSection === "plex"}
                <PlexSection />
              {:else if activeSection === "images"}
                <ImagesSection />
              {:else if activeSection === "tmdb"}
                <TmdbSection />
              {:else if activeSection === "omdb"}
                <OmdbSection />
              {:else if activeSection === "websearch"}
                <WebSearchSection />
              {:else if activeSection === "writeback"}
                <TmdbWritebackSection />
              {:else if activeSection === "local-ai"}
                <LocalAiSection bind:endpoints={aiEndpoints} endpointsError={data.endpointsError} />
              {:else if activeSection === "kinorium-sync"}
                <KinoriumSyncSection endpoints={aiEndpoints} />
              {:else if activeSection === "taste"}
                <TasteSection tastes={data.tastes} tastesError={data.tastesError} />
              {:else if activeSection === "diagnostics"}
                <DiagnosticsSection endpoints={aiEndpoints} />
              {/if}
            </CardContent>
          </Card>
        {/if}
      </div>
    </div>

    <div
      class="bg-background/95 supports-[backdrop-filter]:bg-background/80 sticky bottom-0 z-10 -mx-3 flex flex-wrap items-center justify-between gap-3 border-t px-3 py-3 backdrop-blur md:-mx-4 md:px-4"
    >
      <div class="text-sm">
        {#if dirtyTotal}
          <span class="font-medium">{dirtyTotal}</span>
          {dirtyTotal === 1 ? "несохранённое изменение" : "несохранённых изменений"}
          {#if dirtySectionTitles.length}
            <span class="text-muted-foreground">· {dirtySectionTitles.join(", ")}</span>
          {/if}
        {:else}
          <span class="text-muted-foreground">Все изменения сохранены.</span>
        {/if}
      </div>
      <div class="flex gap-2">
        <Button variant="outline" onclick={store.resetForm} disabled={!store.isDirty || store.isSaving}>
          Reset
        </Button>
        <Button onclick={store.save} disabled={store.isSaving || !store.isDirty}>
          {store.isSaving ? "Saving..." : "Save Preferences"}
        </Button>
      </div>
    </div>

    <Sheet.Root bind:open={navOpen}>
      <Sheet.Content side="left" class="w-72">
        <Sheet.Header>
          <Sheet.Title>Разделы</Sheet.Title>
          <Sheet.Description>Настройки MovieFilter Pro</Sheet.Description>
        </Sheet.Header>
        <div class="overflow-y-auto px-4 pb-6">
          <PreferencesNav
            sections={PREFERENCES_SECTIONS}
            active={activeSection}
            dirtyCounts={dirty}
            missing={missingSections}
            onselect={selectSection}
          />
        </div>
      </Sheet.Content>
    </Sheet.Root>
  </div>
{:else}
  <div class="mx-auto flex w-full max-w-3xl flex-col gap-6 px-3 py-4 md:px-4">
    <Card class="border-destructive/40">
      <CardHeader>
        <CardTitle>Не удалось загрузить Preferences</CardTitle>
        <CardDescription>{store.loadError || "Unknown API error"}</CardDescription>
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
