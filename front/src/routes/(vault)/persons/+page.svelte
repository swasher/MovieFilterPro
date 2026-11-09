<script lang="ts">
  import { goto } from "$app/navigation";
  import "../vault-detail.css";
  import { Card, CardContent, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Input } from "$lib/components/ui/input";
  import { Label } from "$lib/components/ui/label";
  import { Switch } from "$lib/components/ui/switch";
  import { SortSelect } from "$lib/components/ui/sort-select";
  import PersonCard from "$lib/components/vault/PersonCard.svelte";
  import { X } from "@lucide/svelte";

  type ApiPerson = {
    id: number;
    name: string;
    original_name: string | null;
    photo_url: string | null;
    birth_date: string | null;
    death_date: string | null;
    movies_count: number;
    is_favorite: boolean;
    is_star: boolean;
  };

  type HomePersonGroup = {
    id: string;
    title: string;
    see_all_href: string;
    persons: ApiPerson[];
  };

  let { data } = $props();
  const persons = $derived(data.persons ?? []);
  const isHome = $derived(data.isHome === true);
  const homeGroups = $derived(
    ((data.homeGroups ?? []) as HomePersonGroup[]).filter(
      (group) => group.persons.length > 0
    )
  );

  let searchQuery = $state(data.activeQuery ?? "");
  // Обычная переменная, НЕ $state: иначе присвоение в applyParams перезапустит
  // $effect ниже со старым data и затрет ввод (как в Фильмах, коммит 492755b).
  let lastSubmittedSearchQuery = "";
  let onlyFavorites = $state(data.activeIsFavorite ?? false);
  let onlyStars = $state(data.activeIsStar ?? false);
  let useEnglish = $state((data.activeLang ?? "ru") === "en");
  let activeOrder = $state(data.activeOrder ?? "name");
  let searchDebounceHandle = $state<ReturnType<typeof setTimeout> | null>(null);

  $effect(() => {
    const active = data.activeQuery ?? "";
    // Как на странице фильмов: не затираем ввод пользователя эхом из URL
    if (searchQuery === lastSubmittedSearchQuery && active !== lastSubmittedSearchQuery.trim()) {
      searchQuery = active;
    }
    onlyFavorites = data.activeIsFavorite ?? false;
    onlyStars = data.activeIsStar ?? false;
    useEnglish = (data.activeLang ?? "ru") === "en";
    activeOrder = data.activeOrder ?? "name";
  });

  const nameField = $derived(useEnglish ? "original_name" : "name");
  const defaultOrder = $derived(useEnglish ? "original_name" : "name");
  const sortOptions = $derived([
    { field: nameField, label: "По имени" },
    { field: "birth_date", label: "По году рождения" },
    { field: "updated_at", label: "По дате обновления" },
    { field: "movies_count", label: "По числу фильмов" },
    { field: "popularity", label: "По популярности" },
  ]);

  // В EN-режиме основным показываем английское имя (с fallback на русское)
  const displayPerson = (person: ApiPerson): ApiPerson =>
    useEnglish
      ? { ...person, name: person.original_name || person.name, original_name: person.name }
      : person;

  const applyParams = async () => {
    const params = new URLSearchParams();
    const trimmed = searchQuery.trim();
    if (trimmed) params.set("q", trimmed);
    if (onlyFavorites) params.set("is_favorite", "true");
    if (onlyStars) params.set("is_star", "true");
    if (useEnglish) params.set("lang", "en");
    if (activeOrder && activeOrder !== defaultOrder) params.set("order", activeOrder);
    const queryString = params.toString();
    lastSubmittedSearchQuery = searchQuery;
    await goto(queryString ? `/persons?${queryString}` : "/persons", {
      replaceState: true,
      keepFocus: true,
      noScroll: true,
      invalidateAll: true,
    });
  };

  const onSearchInput = () => {
    if (searchDebounceHandle) clearTimeout(searchDebounceHandle);
    searchDebounceHandle = setTimeout(() => {
      void applyParams();
    }, 250);
  };

  const clearSearch = async () => {
    searchQuery = "";
    await applyParams();
  };

  const onOrderChange = async (value: string) => {
    activeOrder = value;
    await applyParams();
  };

  const onFavoritesToggle = async (checked: boolean) => {
    onlyFavorites = checked;
    await applyParams();
  };

  const onStarsToggle = async (checked: boolean) => {
    onlyStars = checked;
    await applyParams();
  };

  const onLangToggle = async (checked: boolean) => {
    useEnglish = checked;
    // Сортировка "по имени" едет за языком, направление сохраняем
    const direction = activeOrder.startsWith("-") ? "-" : "";
    const field = activeOrder.replace(/^-/, "");
    if (field === "name" || field === "original_name") {
      activeOrder = direction + (checked ? "original_name" : "name");
    }
    await applyParams();
  };
</script>

<div class="mx-auto w-full max-w-6xl p-6">
  <div class="mb-6 space-y-3">
    <div class="flex flex-wrap items-center gap-3">
      <div class="relative min-w-[260px] flex-1">
        <Input
          bind:value={searchQuery}
          type="search"
          placeholder="Поиск по имени или псевдониму..."
          class="h-11 w-full pr-10"
          oninput={onSearchInput}
        />
        {#if searchQuery.trim()}
          <button
            type="button"
            class="text-muted-foreground hover:text-foreground absolute right-2 top-1/2 -translate-y-1/2"
            onclick={clearSearch}
            aria-label="Очистить поиск"
          >
            <X class="size-4" />
          </button>
        {/if}
      </div>

      <div class="flex flex-wrap items-center gap-3">
        <SortSelect value={activeOrder} onChange={onOrderChange} options={sortOptions} />

        <div class="flex items-center gap-1.5">
          <Switch id="persons-stars" checked={onlyStars} onCheckedChange={onStarsToggle} />
          <Label
            for="persons-stars"
            class="cursor-pointer select-none font-mono text-[10px] transition-colors duration-150 {onlyStars
              ? 'text-amber-500 font-bold'
              : 'text-muted-foreground/50'}"
          >
            STAR
          </Label>
        </div>

        <div class="flex items-center gap-1.5">
          <Switch id="persons-favorites" checked={onlyFavorites} onCheckedChange={onFavoritesToggle} />
          <Label
            for="persons-favorites"
            class="cursor-pointer select-none font-mono text-[10px] transition-colors duration-150 {onlyFavorites
              ? 'text-primary font-bold'
              : 'text-muted-foreground/50'}"
          >
            FAVORITES
          </Label>
        </div>

        <div class="flex items-center gap-1.5">
          <Switch id="persons-lang" checked={useEnglish} onCheckedChange={onLangToggle} />
          <Label
            for="persons-lang"
            class="cursor-pointer select-none font-mono text-[10px] transition-colors duration-150 {useEnglish
              ? 'text-primary font-bold'
              : 'text-muted-foreground/50'}"
          >
            {useEnglish ? "EN" : "РУ"}
          </Label>
        </div>
      </div>
    </div>

    {#if data.activeQuery || data.activeIsFavorite || data.activeIsStar}
      <div class="flex flex-wrap items-center gap-3 text-sm">
        {#if data.activeIsStar}
          <p class="text-muted-foreground">
            Только звёзды
            <button class="underline hover:text-foreground" onclick={() => onStarsToggle(false)}>×</button>
          </p>
        {/if}
        {#if data.activeIsStar && data.activeIsFavorite}
          <span class="text-border">|</span>
        {/if}
        {#if data.activeIsFavorite}
          <p class="text-muted-foreground">
            Только избранное
            <button
              class="underline hover:text-foreground"
              onclick={() => onFavoritesToggle(false)}>×</button
            >
          </p>
        {/if}
        {#if (data.activeIsFavorite || data.activeIsStar) && data.activeQuery}
          <span class="text-border">|</span>
        {/if}
        {#if data.activeQuery}
          <p class="text-muted-foreground">Поиск: <strong>{data.activeQuery}</strong></p>
        {/if}
      </div>
    {/if}
  </div>

  {#if isHome}
    {#if data.apiError}
      <Card>
        <CardHeader>
          <CardTitle>Ошибка API</CardTitle>
        </CardHeader>
        <CardContent class="vd-card-content">
          <p class="vd-empty">{data.apiError}</p>
        </CardContent>
      </Card>
    {:else if homeGroups.length}
      {#each homeGroups as group, groupIndex (group.id)}
        <div class="mb-8">
          <div class="mb-3 flex items-baseline justify-between gap-4">
            <h2 class="text-lg font-semibold tracking-tight">{group.title}</h2>
            <a
              href={group.see_all_href}
              class="text-muted-foreground shrink-0 text-sm transition-colors hover:text-foreground"
            >
              Все
            </a>
          </div>
          <div class="vd-crew-grid">
            {#each group.persons as person, index (person.id)}
              <PersonCard person={person} priority={groupIndex === 0 && index < 5} />
            {/each}
          </div>
        </div>
      {/each}
    {:else}
      <Card>
        <CardHeader>
          <CardTitle>Персон пока нет</CardTitle>
        </CardHeader>
        <CardContent class="vd-card-content">
          <p class="vd-empty">Персоны появятся после синхронизации фильмов с TMDB.</p>
        </CardContent>
      </Card>
    {/if}
  {:else}
    <Card class="vd-card">
      <CardHeader>
        <CardTitle class="vd-section-title">Все персоны ({persons.length})</CardTitle>
      </CardHeader>
      <CardContent class="vd-card-content">
        {#if data.apiError}
          <p class="vd-empty">{data.apiError}</p>
        {:else if persons.length}
          <div class="vd-crew-grid">
            {#each persons as person, index (person.id)}
              <PersonCard person={displayPerson(person)} priority={index < 5} />
            {/each}
          </div>
        {:else}
          <p class="vd-empty">Нет данных</p>
        {/if}
      </CardContent>
    </Card>
  {/if}
</div>
