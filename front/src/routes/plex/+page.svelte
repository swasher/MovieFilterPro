<script lang="ts">
  import { onMount } from "svelte";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "$lib/components/ui/card";
  import { Badge } from "$lib/components/ui/badge";
  import { 
    Loader2, 
    Library, 
    Film, 
    Search,
    Video,
    Calendar,
    Settings,
    AlertCircle,
    Info,
    RefreshCw
  } from "@lucide/svelte";
  import { toast } from "svelte-sonner";

  interface PlexMovie {
    title: string;
    original_title: string | null;
    file_name: string | null;
    file_path: string | null;
    year: number | null;
    guids: string[];
  }

  let sections = $state<string[]>([]);
  let selectedSection = $state<string | null>(null);
  let movies = $state<PlexMovie[]>([]);
  let isLoadingSections = $state(false);
  let isLoadingMovies = $state(false);
  let searchQuery = $state("");
  let errorMessage = $state<string | null>(null);

  // Load Plex libraries (sections)
  async function loadSections() {
    isLoadingSections = true;
    let errorMessage: string = '';
    selectedSection = null;
    movies = [];
    try {
      const res = await fetch("/api/plex/sections");
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Ошибка ${res.status}`);
      }
      sections = await res.json();
      if (sections.length > 0) {
        await selectSection(sections[0]);
      }
    } catch (err: any) {
      console.error(err);
      errorMessage = err.message || "Не удалось загрузить библиотеки Plex. Проверьте настройки подключения.";
      toast.error(errorMessage);
    } finally {
      isLoadingSections = false;
    }
  }

  // Select section and load movies
  async function selectSection(section: string) {
    selectedSection = section;
    isLoadingMovies = true;
    movies = [];
    searchQuery = "";
    try {
      const res = await fetch(`/api/plex/sections/${encodeURIComponent(section)}/movies`);
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Ошибка ${res.status}`);
      }
      movies = await res.json();
    } catch (err: any) {
      console.error(err);
      toast.error(`Не удалось загрузить фильмы библиотеки "${section}": ${err.message}`);
    } finally {
      isLoadingMovies = false;
    }
  }

  // Deriving filtered movies reactively in Svelte 5
  const filteredMovies = $derived(
    searchQuery.trim() === ""
      ? movies
      : movies.filter(m => {
          const query = searchQuery.toLowerCase();
          return (
            m.title.toLowerCase().includes(query) ||
            (m.original_title && m.original_title.toLowerCase().includes(query)) ||
            (m.file_name && m.file_name.toLowerCase().includes(query))
          );
        })
  );

  // Parse GUIDs to readable formats
  function getGuidBadgeInfo(guid: string) {
    if (guid.includes("://")) {
      const [type, id] = guid.split("://");
      let typeLabel = type.toUpperCase();
      let colorClass = "bg-muted text-muted-foreground border-border";
      
      if (type === "imdb") {
        colorClass = "bg-amber-500/10 text-amber-500 border-amber-500/20";
      } else if (type === "tmdb") {
        colorClass = "bg-emerald-500/10 text-emerald-500 border-emerald-500/20";
      } else if (type === "tvdb") {
        colorClass = "bg-blue-500/10 text-blue-500 border-blue-500/20";
      } else if (type === "plex") {
        colorClass = "bg-orange-500/10 text-orange-500 border-orange-500/20";
      }
      
      return { type: typeLabel, id, colorClass };
    }
    return { type: "GUID", id: guid, colorClass: "bg-muted text-muted-foreground border-border" };
  }

  onMount(() => {
    loadSections();
  });
</script>

<div class="container mx-auto p-6 space-y-6">
  <!-- Header -->
  <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
    <div>
      <h1 class="text-3xl font-extrabold tracking-tight flex items-center gap-2">
        <Library class="w-8 h-8 text-orange-500" />
        Plex Библиотека
      </h1>
      <p class="text-muted-foreground mt-1">Просмотр и поиск медиафайлов на вашем Plex сервере</p>
    </div>
    
    <div class="flex items-center gap-2">
      <Button variant="outline" size="sm" onclick={loadSections} disabled={isLoadingSections || isLoadingMovies}>
        <RefreshCw class="w-4 h-4 mr-2 {isLoadingSections ? 'animate-spin' : ''}" />
        Обновить
      </Button>
      <Button variant="outline" size="sm" href="/preferences">
        <Settings class="w-4 h-4 mr-2" />
        Настройки
      </Button>
    </div>
  </div>

  {#if errorMessage}
    <Card class="border-destructive/50 bg-destructive/5">
      <CardHeader>
        <div class="flex items-center gap-2 text-destructive">
          <AlertCircle class="w-5 h-5" />
          <CardTitle>Ошибка подключения</CardTitle>
        </div>
        <CardDescription class="text-destructive-foreground/80">
          {errorMessage}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div class="flex gap-4">
          <Button variant="destructive" onclick={loadSections}>Повторить попытку</Button>
          <Button variant="outline" href="/preferences">Перейти в настройки Plex</Button>
        </div>
      </CardContent>
    </Card>
  {:else}
    <!-- Sections Selector -->
    <Card class="bg-card/50 backdrop-blur-sm border-border">
      <CardHeader class="pb-3">
        <CardTitle class="text-lg font-semibold flex items-center gap-2">
          <Video class="w-5 h-5 text-orange-500" />
          Выберите библиотеку Plex
        </CardTitle>
      </CardHeader>
      <CardContent>
        {#if isLoadingSections}
          <div class="flex items-center gap-2 text-muted-foreground py-2">
            <Loader2 class="w-4 h-4 animate-spin" />
            <span>Загрузка библиотек...</span>
          </div>
        {:else if sections.length === 0}
          <div class="flex items-center gap-2 text-muted-foreground py-2">
            <Info class="w-4 h-4" />
            <span>Нет доступных библиотек. Убедитесь, что Plex настроен корректно.</span>
          </div>
        {:else}
          <div class="flex flex-wrap gap-2">
            {#each sections as section}
              <Button
                variant={selectedSection === section ? "default" : "outline"}
                onclick={() => selectSection(section)}
                class="transition-all duration-200"
              >
                {section}
              </Button>
            {/each}
          </div>
        {/if}
      </CardContent>
    </Card>

    <!-- Movies List -->
    {#if selectedSection}
      <Card class="border-border">
        <CardHeader class="pb-3 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <CardTitle class="text-xl font-bold flex items-center gap-2">
              <Film class="w-5 h-5 text-primary" />
              {selectedSection}
            </CardTitle>
            <CardDescription>
              {#if isLoadingMovies}
                Загрузка фильмов...
              {:else}
                Всего найдено: <span class="font-bold text-foreground">{movies.length}</span>
                {#if searchQuery}
                  (отфильтровано: <span class="font-bold text-primary">{filteredMovies.length}</span>)
                {/if}
              {/if}
            </CardDescription>
          </div>

          <!-- Search Input -->
          {#if !isLoadingMovies && movies.length > 0}
            <div class="relative w-full md:w-80">
              <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Поиск по названию или файлу..."
                bind:value={searchQuery}
                class="pl-9 bg-background"
              />
            </div>
          {/if}
        </CardHeader>
        
        <CardContent class="p-0 md:p-6">
          {#if isLoadingMovies}
            <div class="flex flex-col items-center justify-center py-12 space-y-4">
              <Loader2 class="w-8 h-8 animate-spin text-orange-500" />
              <p class="text-sm text-muted-foreground">Загрузка фильмов с Plex сервера...</p>
            </div>
          {:else if movies.length === 0}
            <div class="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Film class="w-12 h-12 mb-3 stroke-[1.5]" />
              <p>В этой библиотеке нет фильмов</p>
            </div>
          {:else if filteredMovies.length === 0}
            <div class="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Search class="w-12 h-12 mb-3 stroke-[1.5]" />
              <p>По вашему запросу ничего не найдено</p>
            </div>
          {:else}
            <!-- Responsive Table Container -->
            <div class="relative w-full overflow-x-auto rounded-lg border border-border bg-card">
              <table class="w-full caption-bottom text-sm border-collapse">
                <thead class="bg-muted/50 border-b border-border">
                  <tr>
                    <th class="h-12 px-4 text-left align-middle font-semibold text-muted-foreground w-12">#</th>
                    <th class="h-12 px-4 text-left align-middle font-semibold text-muted-foreground min-w-[200px]">Название</th>
                    <th class="h-12 px-4 text-left align-middle font-semibold text-muted-foreground min-w-[200px]">Оригинальное название</th>
                    <th class="h-12 px-4 text-left align-middle font-semibold text-muted-foreground min-w-[250px]">Файл</th>
                    <th class="h-12 px-4 text-left align-middle font-semibold text-muted-foreground w-24">Год</th>
                    <th class="h-12 px-4 text-left align-middle font-semibold text-muted-foreground w-64">IDs</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-border">
                  {#each filteredMovies as movie, idx}
                    <tr class="hover:bg-muted/30 transition-colors duration-150">
                      <td class="px-4 py-3 align-middle font-medium text-muted-foreground">{idx + 1}</td>
                      <td class="px-4 py-3 align-middle font-semibold text-foreground">
                        {movie.title}
                      </td>
                      <td class="px-4 py-3 align-middle text-muted-foreground italic">
                        {movie.original_title || "—"}
                      </td>
                      <td class="px-4 py-3 align-middle">
                        {#if movie.file_name}
                          <span class="font-mono text-xs block text-foreground truncate max-w-xs md:max-w-md" title={movie.file_path}>
                            {movie.file_name}
                          </span>
                          {#if movie.file_path && movie.file_path !== movie.file_name}
                            <span class="text-[10px] text-muted-foreground block truncate max-w-xs md:max-w-md" title={movie.file_path}>
                              {movie.file_path}
                            </span>
                          {/if}
                        {:else}
                          <span class="text-muted-foreground">—</span>
                        {/if}
                      </td>
                      <td class="px-4 py-3 align-middle">
                        {#if movie.year}
                          <span class="inline-flex items-center gap-1">
                            <Calendar class="w-3.5 h-3.5 text-muted-foreground" />
                            {movie.year}
                          </span>
                        {:else}
                          <span class="text-muted-foreground">—</span>
                        {/if}
                      </td>
                      <td class="px-4 py-3 align-middle">
                        <div class="flex flex-wrap gap-1">
                          {#if movie.guids && movie.guids.length > 0}
                            {#each movie.guids as guid}
                              {@const badge = getGuidBadgeInfo(guid)}
                              <Badge variant="outline" class="text-[10px] py-0.5 px-1.5 font-mono {badge.colorClass}">
                                {badge.type}: {badge.id}
                              </Badge>
                            {/each}
                          {:else}
                            <span class="text-xs text-muted-foreground">—</span>
                          {/if}
                        </div>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
        </CardContent>
      </Card>
    {/if}
  {/if}
</div>
