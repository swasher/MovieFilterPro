<script lang="ts">
  import { LoaderCircle } from "@lucide/svelte";
  import { cn } from "$lib/utils";
  import * as ImageZoom from "$lib/components/ui/image-zoom";

  type Props = {
    src: string | null | undefined;
    alt?: string;
    class?: string;
    /** Классы слота-обёртки: размеры и скругления конкретного места. */
    slotClass?: string;
    /** Если задан — картинка открывается в ImageZoom (нужен ImageZoom.Root выше). */
    zoomSrc?: string | null;
    spinnerClass?: string;
    loading?: "eager" | "lazy";
    decoding?: "sync" | "async" | "auto";
    /** Приоритет загрузки: high — для LCP-картинок первого экрана. */
    fetchpriority?: "high" | "low" | "auto";
    title?: string;
  };

  let {
    src,
    alt = "",
    class: className,
    slotClass,
    zoomSrc = null,
    spinnerClass = "size-4",
    loading,
    decoding,
    fetchpriority,
    title
  }: Props = $props();

  let loaded = $state(false);
  let showSpinner = $state(false);
  let spinnerTimer: ReturnType<typeof setTimeout> | null = null;

  $effect(() => {
    // Новый источник — снова ждём загрузку. Спиннер показываем с задержкой:
    // мгновенные (закешированные браузером) картинки не должны мигать.
    src;
    loaded = false;
    showSpinner = false;

    spinnerTimer = setTimeout(() => {
      if (!loaded) {
        showSpinner = true;
      }
    }, 150);

    return () => {
      if (spinnerTimer) {
        clearTimeout(spinnerTimer);
        spinnerTimer = null;
      }
    };
  });

  function handleLoad() {
    loaded = true;
  }

  function handleError() {
    // Не крутим спиннер вечно, если картинки нет.
    loaded = true;
  }
</script>

<div class={cn("vault-image-slot", slotClass)}>
  {#if zoomSrc}
    <ImageZoom.Trigger
      src={src ?? ""}
      {alt}
      {zoomSrc}
      class={className}
      {loading}
      {decoding}
      {fetchpriority}
      {title}
      onload={handleLoad}
      onerror={handleError}
    />
  {:else}
    <img
      src={src ?? ""}
      {alt}
      class={className}
      {loading}
      {decoding}
      {fetchpriority}
      {title}
      onload={handleLoad}
      onerror={handleError}
    />
  {/if}
  {#if showSpinner}
    <div class="vault-image-overlay" class:vault-image-overlay--hidden={loaded} aria-hidden="true">
      <LoaderCircle class={cn("vault-image-spinner", spinnerClass)} />
    </div>
  {/if}
</div>

<style>
  .vault-image-slot {
    position: relative;
  }

  .vault-image-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--muted);
    opacity: 1;
    transition: opacity 300ms ease;
    pointer-events: none;
  }

  .vault-image-overlay--hidden {
    opacity: 0;
  }

  .vault-image-spinner {
    color: var(--muted-foreground);
    opacity: 0.75;
    animation: vault-image-spin 1s linear infinite;
  }

  @keyframes vault-image-spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
