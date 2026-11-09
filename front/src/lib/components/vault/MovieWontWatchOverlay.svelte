<script lang="ts">
  import { X } from "@lucide/svelte";
  import "./movie-wont-watch-overlay.css";

  let {
    watch_status,
    size = "md"
  }: {
    watch_status: "watched" | "will_watch" | "wont_watch" | null;
    size?: "xs" | "md";
  } = $props();
</script>

{#if watch_status === "wont_watch"}
  <div
    class="vd-wont-watch-overlay"
    class:vd-wont-watch-overlay--xs={size === "xs"}
    aria-hidden="true"
  >
    {#if size === "xs"}
      <X class="size-3.5" />
    {/if}
  </div>
{/if}
