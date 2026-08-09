<script lang="ts">
  import * as Popover from "$lib/components/ui/popover";
  import * as StarRating from "$lib/components/ui/star-rating";
  import { CheckCheck } from "@lucide/svelte";
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

  const isWatched = $derived(season.user_state.watch_status === "watched");
  const hasRating = $derived(season.user_state.rating !== null);
  const currentRating = $derived(season.user_state.rating ?? 0);

  const triggerClass = cn(
    "vd-season-watched",
    isWatched ? "vd-season-watched--active" : "vd-season-watched--inactive"
  );
</script>

<Popover.Root>
  <Popover.Trigger class={triggerClass} onclick={() => onStatusClick(season)} openOnHover>
    {#if hasRating}
      <span class="text-emerald-600 font-medium text-sm">{currentRating}</span>
    {:else if isWatched}
      <CheckCheck class="size-4" />
    {:else}
      <CheckCheck class="size-4 opacity-0" />
    {/if}
  </Popover.Trigger>

  <Popover.Content class="w-56" side="bottom" align="center">
    <div class="p-2">
      <StarRating.Root
        value={currentRating / 2}
        max={5}
        allowHalf
        class="text-amber-500"
        onValueChange={(value) => onRatingClick(season, Math.round(value * 2))}
      >
        {#snippet children({ items })}
          <div class="flex gap-1">
            {#each items as item (item.index)}
              <StarRating.Star index={item.index} state={item.state} class="size-5" />
            {/each}
          </div>
        {/snippet}
      </StarRating.Root>

      {#if hasRating}
        <div class="flex justify-center gap-2 mt-2">
          <span class="text-sm text-muted-foreground">
            Текущая: {currentRating} / 10
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
        <div class="text-center text-sm text-muted-foreground mt-2">
          {currentRating} / 10
        </div>
      {/if}
    </div>
  </Popover.Content>
</Popover.Root>