<script lang="ts">
  import ActivityIcon from "@lucide/svelte/icons/activity";
  import BotIcon from "@lucide/svelte/icons/bot";
  import ClapperboardIcon from "@lucide/svelte/icons/clapperboard";
  import CpuIcon from "@lucide/svelte/icons/cpu";
  import DatabaseIcon from "@lucide/svelte/icons/database";
  import DownloadIcon from "@lucide/svelte/icons/download";
  import FilmIcon from "@lucide/svelte/icons/film";
  import FunnelIcon from "@lucide/svelte/icons/funnel";
  import ImageIcon from "@lucide/svelte/icons/image";
  import LockIcon from "@lucide/svelte/icons/lock";
  import MonitorPlayIcon from "@lucide/svelte/icons/monitor-play";
  import RefreshCwIcon from "@lucide/svelte/icons/refresh-cw";
  import SearchIcon from "@lucide/svelte/icons/search";
  import SparklesIcon from "@lucide/svelte/icons/sparkles";
  import StarIcon from "@lucide/svelte/icons/star";
  import { Badge } from "$lib/components/ui/badge";
  import { cn } from "$lib/utils.js";
  import type { PreferencesSection, PreferencesSectionId } from "./types.js";

  type Props = {
    sections: PreferencesSection[];
    active: PreferencesSectionId;
    dirtyCounts?: Map<PreferencesSectionId, number>;
    missing?: PreferencesSectionId[];
    onselect: (id: PreferencesSectionId) => void;
  };

  let { sections, active, dirtyCounts = new Map(), missing = [], onselect }: Props = $props();

  const ICONS: Record<PreferencesSectionId, typeof ActivityIcon> = {
    kinozal: ClapperboardIcon,
    rules: FunnelIcon,
    qbittorrent: DownloadIcon,
    plex: MonitorPlayIcon,
    images: ImageIcon,
    player: FilmIcon,
    tmdb: DatabaseIcon,
    omdb: StarIcon,
    websearch: SearchIcon,
    writeback: RefreshCwIcon,
    "local-ai": CpuIcon,
    "kinorium-sync": BotIcon,
    taste: SparklesIcon,
    account: LockIcon,
    diagnostics: ActivityIcon
  };

  const groups = $derived([...new Set(sections.map((item) => item.group))]);
</script>

<nav class="flex flex-col gap-5" aria-label="Разделы preferences">
  {#each groups as group (group)}
    <div class="space-y-1">
      <div class="text-muted-foreground px-2 text-[0.7rem] font-medium tracking-[0.14em] uppercase">
        {group}
      </div>
      {#each sections.filter((item) => item.group === group) as section (section.id)}
        {@const Icon = ICONS[section.id]}
        {@const dirtyCount = dirtyCounts.get(section.id) ?? 0}
        <button
          type="button"
          class={cn(
            "hover:bg-accent/70 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-start text-sm transition-colors",
            active === section.id && "bg-secondary text-secondary-foreground font-medium"
          )}
          aria-current={active === section.id ? "page" : undefined}
          onclick={() => onselect(section.id)}
        >
          <Icon class="size-4 shrink-0 opacity-70" />
          <span class="min-w-0 flex-1 truncate">{section.title}</span>
          {#if dirtyCount}
            <Badge
              variant="outline"
              class="shrink-0 border-amber-500/40 tabular-nums text-amber-600 dark:text-amber-400"
              title="Несохранённых изменений"
            >
              {dirtyCount}
            </Badge>
          {:else if missing.includes(section.id)}
            <span class="bg-destructive/70 size-2 shrink-0 rounded-full" title="Не настроено"></span>
          {/if}
        </button>
      {/each}
    </div>
  {/each}
</nav>
