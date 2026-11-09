<script lang="ts" module>
  export type FilmographyItem = {
    id: number;
    title: string;
    slug: string;
    year: number | null;
    poster_url: string | null;
    roles: string[];
    character_names: string[];
    watch_status: "watched" | "will_watch" | "wont_watch" | null;
    rating: number | null;
    is_favorite: boolean;
  };
</script>

<script lang="ts">
  import { Badge } from "$lib/components/ui/badge";
  import { Button } from "$lib/components/ui/button";
  import * as ButtonGroup from "$lib/components/ui/button-group";
  import { Card, CardContent, CardHeader, CardTitle } from "$lib/components/ui/card";
  import * as Table from "$lib/components/ui/table";
  import {
    Bookmark,
    CalendarDays,
    Check,
    Heart,
    LayoutGrid,
    ListChecks,
    Rows3,
    Table2,
    X
  } from "@lucide/svelte";
  import MovieStatusBadges from "./MovieStatusBadges.svelte";
  import MovieWontWatchOverlay from "./MovieWontWatchOverlay.svelte";
  import VaultImage from "./VaultImage.svelte";

  let { filmography }: { filmography: FilmographyItem[] } = $props();

  type ViewMode = "grid" | "table";
  type GroupMode = "none" | "year" | "status";

  let viewMode = $state<ViewMode>("grid");
  let groupMode = $state<GroupMode>("status");

  const statusGroupOrder = ["will_watch", "watched", "wont_watch", "none"] as const;

  const statusGroupLabels: Record<(typeof statusGroupOrder)[number], string> = {
    will_watch: "БУДУ СМОТРЕТЬ",
    watched: "ПРОСМОТРЕНО",
    wont_watch: "НЕ БУДУ СМОТРЕТЬ",
    none: "Без статуса"
  };

  type FilmographyGroup = {
    key: string;
    label: string;
    items: FilmographyItem[];
  };

  const groups = $derived.by<FilmographyGroup[]>(() => {
    if (groupMode === "none") {
      return [{ key: "all", label: "", items: filmography }];
    }

    if (groupMode === "year") {
      const byYear = new Map<string, FilmographyItem[]>();
      for (const item of filmography) {
        const key = item.year != null ? String(item.year) : "no-year";
        const bucket = byYear.get(key);
        if (bucket) {
          bucket.push(item);
        } else {
          byYear.set(key, [item]);
        }
      }

      return Array.from(byYear, ([key, items]) => ({
        key,
        label: key === "no-year" ? "Без года" : key,
        items
      }));
    }

    const byStatus = new Map<string, FilmographyItem[]>();
    for (const item of filmography) {
      const key = item.watch_status ?? "none";
      const bucket = byStatus.get(key);
      if (bucket) {
        bucket.push(item);
      } else {
        byStatus.set(key, [item]);
      }
    }

    return statusGroupOrder.flatMap((key) => {
      const items = byStatus.get(key);
      return items?.length ? [{ key, label: statusGroupLabels[key], items }] : [];
    });
  });
</script>

{#snippet filmographyGrid(items: FilmographyItem[])}
  <div class="vd-filmography-grid">
    {#each items as item (`${item.id}`)}
      <a href={`/movies/${item.slug}`} data-sveltekit-preload-data="hover" class="block">
        <div class="vd-filmography-card">
          <div class="relative">
            {#if item.poster_url}
              <VaultImage src={item.poster_url} alt={item.title} class="vd-poster" slotClass="w-full" loading="lazy" decoding="async" />
            {:else}
              <div class="vd-poster-fallback">
                no poster
              </div>
            {/if}
            <MovieStatusBadges
              watch_status={item.watch_status}
              rating={item.rating}
              is_favorite={item.is_favorite}
              year={item.year}
            />
          </div>

          <div class="vd-filmography-copy">
            <p class="vd-related-title">{item.title}</p>
            <div class="vd-facts-row vd-facts-row--muted">
              <span class="vd-fact-inline">{item.roles.join(", ")}</span>
            </div>
            {#if item.character_names.length}
              <p class="vd-related-subtitle">{item.character_names.join(", ")}</p>
            {/if}
          </div>
        </div>
      </a>
    {/each}
  </div>
{/snippet}

{#snippet filmographyTable(items: FilmographyItem[])}
  <div class="overflow-hidden rounded-xl border border-border/50">
    <Table.Root>
      <Table.Header class="bg-muted/60">
        <Table.Row class="hover:bg-transparent">
          <Table.Head class="w-14 px-2">Poster</Table.Head>
          <Table.Head class="px-3">Title</Table.Head>
          <Table.Head class="w-20 px-3">Year</Table.Head>
          <Table.Head class="px-3">Roles</Table.Head>
          <Table.Head class="px-3">Character</Table.Head>
          <Table.Head class="w-24 px-3">Status</Table.Head>
        </Table.Row>
      </Table.Header>
      <Table.Body>
        {#each items as item (`${item.id}`)}
          <Table.Row class="hover:bg-accent/20">
            <Table.Cell class="px-2">
              <a
                href={`/movies/${item.slug}`}
                data-sveltekit-preload-data="hover"
                class="relative block h-14 w-10 overflow-hidden rounded"
              >
                {#if item.poster_url}
                  <VaultImage
                    src={item.poster_url}
                    alt={item.title}
                    class="h-full w-full object-cover"
                    slotClass="h-full w-full"
                    loading="lazy"
                  />
                {:else}
                  <div
                    class="bg-muted text-muted-foreground flex h-full w-full items-center justify-center text-[10px]"
                  >
                    no
                  </div>
                {/if}
                <MovieWontWatchOverlay watch_status={item.watch_status} size="xs" />
              </a>
            </Table.Cell>
            <Table.Cell class="px-3 font-medium whitespace-normal">
              <a href={`/movies/${item.slug}`} data-sveltekit-preload-data="hover">
                {item.title}
              </a>
            </Table.Cell>
            <Table.Cell class="px-3">{item.year ?? "—"}</Table.Cell>
            <Table.Cell class="text-muted-foreground px-3 whitespace-normal">
              {item.roles.join(", ")}
            </Table.Cell>
            <Table.Cell class="text-muted-foreground px-3 whitespace-normal">
              {item.character_names.join(", ") || "—"}
            </Table.Cell>
            <Table.Cell class="px-3">
              <div class="flex items-center gap-1.5">
                {#if item.watch_status === "watched"}
                  <span
                    class="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400"
                    title="Просмотрено"
                  >
                    <Check class="size-3.5" />
                    {#if item.rating !== null}
                      <span class="text-xs tabular-nums">{item.rating}</span>
                    {/if}
                  </span>
                {:else if item.watch_status === "will_watch"}
                  <span class="text-orange-500" title="Буду смотреть">
                    <Bookmark class="size-3.5" />
                  </span>
                {:else if item.watch_status === "wont_watch"}
                  <span class="text-red-500" title="Не буду смотреть">
                    <X class="size-3.5" />
                  </span>
                {/if}
                {#if item.is_favorite}
                  <span class="text-red-500" title="Любимое">
                    <Heart class="size-3.5 fill-current" />
                  </span>
                {/if}
                {#if !item.watch_status && !item.is_favorite}
                  <span class="text-muted-foreground">—</span>
                {/if}
              </div>
            </Table.Cell>
          </Table.Row>
        {/each}
      </Table.Body>
    </Table.Root>
  </div>
{/snippet}

<Card class="vd-card">
  <CardHeader>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <CardTitle class="text-xl">Filmography</CardTitle>

      <div class="flex flex-wrap items-center gap-2">
        <ButtonGroup.Root class="shrink-0">
          <Button
            variant={viewMode === "grid" ? "default" : "outline"}
            onclick={() => (viewMode = "grid")}
            title="Сетка постеров"
            aria-label="Сетка постеров"
            aria-pressed={viewMode === "grid"}
          >
            <LayoutGrid class="size-4" />
          </Button>
          <Button
            variant={viewMode === "table" ? "default" : "outline"}
            onclick={() => (viewMode = "table")}
            title="Табличный вид"
            aria-label="Табличный вид"
            aria-pressed={viewMode === "table"}
          >
            <Table2 class="size-4" />
          </Button>
        </ButtonGroup.Root>

        <ButtonGroup.Root class="shrink-0">
          <Button
            variant={groupMode === "none" ? "default" : "outline"}
            onclick={() => (groupMode = "none")}
            title="Без разбиения"
            aria-label="Без разбиения"
            aria-pressed={groupMode === "none"}
          >
            <Rows3 class="size-4" />
            <span class="hidden sm:inline">Без разбиения</span>
          </Button>
          <Button
            variant={groupMode === "year" ? "default" : "outline"}
            onclick={() => (groupMode = "year")}
            title="Разбить по годам"
            aria-label="Разбить по годам"
            aria-pressed={groupMode === "year"}
          >
            <CalendarDays class="size-4" />
            <span class="hidden sm:inline">По годам</span>
          </Button>
          <Button
            variant={groupMode === "status" ? "default" : "outline"}
            onclick={() => (groupMode = "status")}
            title="Разбить по статусу"
            aria-label="Разбить по статусу"
            aria-pressed={groupMode === "status"}
          >
            <ListChecks class="size-4" />
            <span class="hidden sm:inline">По статусу</span>
          </Button>
        </ButtonGroup.Root>
      </div>
    </div>
  </CardHeader>
  <CardContent class="vd-card-content">
    {#if filmography.length}
      <div class="space-y-6">
        {#each groups as group (group.key)}
          <section class="space-y-3">
            {#if group.label}
              <div class="flex items-center gap-2">
                <h3 class="text-base font-semibold">{group.label}</h3>
                <Badge variant="secondary">{group.items.length}</Badge>
              </div>
            {/if}

            {#if viewMode === "grid"}
              {@render filmographyGrid(group.items)}
            {:else}
              {@render filmographyTable(group.items)}
            {/if}
          </section>
        {/each}
      </div>
    {:else}
      <p class="vd-empty">No filmography yet.</p>
    {/if}
  </CardContent>
</Card>
