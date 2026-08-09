<script lang="ts">
  import * as Popover from "$lib/components/ui/popover";
  import { CheckCheck, Star } from "@lucide/svelte";
  import { cn } from "$lib/utils.js";

  interface SeasonUserState {
    watch_status: "watched" | "plan" | "skip" | null;
    rating: number | null;
  }

  interface Season {
    id: number;
    user_state: SeasonUserState;
  }

  interface Props {
    season: Season;
    onStatusClick: (season: Season) => void;
    onRatingClick: (season: Season, rating: number | null) => void;
  }

  let { season, onStatusClick, onRatingClick } = $props();

  let hoverRating = $state(0);

  const isWatched = season.user_state.watch_status === "watched";
  const hasRating = season.user_state.rating !== null;

  const triggerClass = cn(
    "vd-season-watched",
    isWatched ? "vd-season-watched--active" : "vd-season-watched--inactive"
  );
</script>

<Popover.Root>
  <Popover.Trigger openOnHover class={triggerClass} onclick={() => onStatusClick(season)}>
    {#if hasRating}
      <span class="text-emerald-600 font-medium text-sm">{season.user_state.rating}</span>
    {:else if isWatched}
      <CheckCheck class="size-4" />
    {:else}
      <CheckCheck class="size-4 opacity-0" />
    {/if}
  </Popover.Trigger>

  <Popover.Content class="w-64" side="bottom" align="center">
    <div class="space-y-3 p-2">

      <div class="flex gap-1 justify-center">
        {#each Array(10) as _, i}
          {@const value = i + 1}
          {@const isFilled = value <= (hoverRating || (season.user_state.rating ?? 0))}
          <button
            type="button"
            aria-label={`Rate ${value} out of 10`}
            class="transition-colors p-1"
            onmouseenter={() => hoverRating = value}
            onmouseleave={() => hoverRating = 0}
            onclick={() => onRatingClick(season, value)}
          >
            <Star
              class={isFilled ? "size-5 fill-current text-amber-500" : "size-5 text-muted-foreground"}
            />
          </button>
        {/each}
      </div>

      {#if hasRating}
        <div class="flex justify-center gap-2">
          <span class="text-sm text-muted-foreground">
            Текущая: {season.user_state.rating} / 10
          </span>
          <button
            type="button"
            class="text-xs text-muted-foreground hover:text-foreground underline"
            onclick={() => onRatingClick(season, null)}
          >
            Сбросить
          </button>
        </div>
      {:else}
        <div class="text-center text-sm text-muted-foreground">
          {hoverRating || (season.user_state.rating ?? 0)} / 10
        </div>
      {/if}
    </div>
  </Popover.Content>
</Popover.Root>