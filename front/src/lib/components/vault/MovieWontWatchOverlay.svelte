<script lang="ts">
  import { X } from "@lucide/svelte";
  import "./movie-wont-watch-overlay.css";

  // Единая точка правки текста плашки.
  // В Vault статус называется «Не интересует»
  // (в выгрузке Kinorium — «Не буду смотреть»).
  const WONT_WATCH_LABEL = "Не интересует";

  let {
    watch_status,
    size = "md"
  }: {
    watch_status: "watched" | "will_watch" | "wont_watch" | null;
    size?: "xs" | "md" | "lg";
  } = $props();
</script>

{#if watch_status === "wont_watch"}
  <div
    class="vd-wont-watch-overlay"
    class:vd-wont-watch-overlay--xs={size === "xs"}
    class:vd-wont-watch-overlay--lg={size === "lg"}
    aria-hidden="true"
  >
    {#if size === "xs"}
      <X class="size-3.5" />
    {:else}
      <span class="vd-wont-watch-plaque">{WONT_WATCH_LABEL}</span>
    {/if}
  </div>
{/if}
