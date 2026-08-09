<script lang="ts">
  import * as Popover from "$lib/components/ui/popover";
  import * as StarRating from "$lib/components/ui/star-rating";
  import { CheckCheck, X } from "@lucide/svelte";
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
    revision: number;
    onStatusClick: (season: Season) => void;
    onRatingClick: (season: Season, rating: number | null) => void;
  }

  let { season, revision, onStatusClick, onRatingClick } = $props();

  let open = $state(false);

  const isWatched = $derived.by(() => {
    revision;
    return season.user_state.watch_status === "watched";
  });
  const hasRating = $derived.by(() => {
    revision;
    return season.user_state.rating !== null;
  });
  const currentRating = $derived.by(() => {
    revision;
    return season.user_state.rating ?? 0;
  });

  const triggerClass = $derived(
    cn(
      "vd-season-watched",
      isWatched ? "vd-season-watched--active" : "vd-season-watched--inactive"
    )
  );

  const handleRatingChange = (value: number) => {
    onRatingClick(season, Math.round(value * 2));
    open = false;
  };

  const handleClearRating = () => {
    onRatingClick(season, null);
    open = false;
  };
</script>

<Popover.Root bind:open>
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
      <div class="flex items-center justify-center gap-2">
        <StarRating.Root
          value={currentRating / 2}
          max={5}
          allowHalf
          class="text-amber-500"
          onValueChange={handleRatingChange}
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
          <button
            type="button"
            class="text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Сбросить оценку"
            onclick={handleClearRating}
          >
            <X class="size-4" />
          </button>
        {/if}
      </div>
    </div>
  </Popover.Content>
</Popover.Root>