<script lang="ts">
  import { Bookmark, Check, Heart, X } from "@lucide/svelte";
  import { cn } from "$lib/utils.js";
  import "./movie-status-badges.css";

  let {
    watch_status,
    rating,
    is_favorite,
    position = "bottom-left"
  }: {
    watch_status: "watched" | "will_watch" | "wont_watch" | null;
    rating: number | null;
    is_favorite: boolean;
    position?: "bottom-left" | "top-left";
  } = $props();

  const statusClass = $derived(
    cn("vd-status-badge", position === "top-left" && "vd-status-badge--top-left")
  );
</script>

{#if watch_status === "wont_watch"}
  <span class={cn(statusClass, "vd-status-badge--wont")} title="Не интересует">
    <X class="size-3" />
  </span>
{:else if watch_status === "will_watch"}
  <span class={cn(statusClass, "vd-status-badge--will")} title="Буду смотреть">
    <Bookmark class="size-3" />
  </span>
{:else if watch_status === "watched"}
  <span class={cn(statusClass, "vd-status-badge--watched")} title="Просмотрено">
    {#if rating !== null}
      <span class="vd-status-badge-rating">{rating}</span>
    {:else}
      <Check class="size-3" />
    {/if}
  </span>
{/if}
{#if is_favorite}
  <span class="vd-status-badge vd-status-badge--favorite" title="Любимое">
    <Heart class="size-3.5 vd-status-badge-heart" />
  </span>
{/if}