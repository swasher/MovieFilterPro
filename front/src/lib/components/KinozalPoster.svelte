<script lang="ts">
  import { Skeleton } from "$lib/components/ui/skeleton";
  import { cn } from "$lib/utils";

  let {
    src,
    alt,
    containerClass = "h-36 w-24",
    imageClass = "",
    fallbackLabel = "no poster"
  }: {
    src: string | null;
    alt: string;
    containerClass?: string;
    imageClass?: string;
    fallbackLabel?: string;
  } = $props();

  let container = $state<HTMLDivElement | null>(null);
  let shouldLoad = $state(false);
  let isLoaded = $state(false);
  let hasError = $state(false);

  $effect(() => {
    src;
    shouldLoad = false;
    isLoaded = false;
    hasError = false;
  });

  $effect(() => {
    const node = container;

    if (!node || !src || shouldLoad) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            shouldLoad = true;
            observer.disconnect();
            break;
          }
        }
      },
      {
        rootMargin: "300px 0px"
      }
    );

    observer.observe(node);

    return () => {
      observer.disconnect();
    };
  });
</script>

<div
  bind:this={container}
  class={cn(
    "relative overflow-hidden rounded-md border border-border/60 bg-muted/40 shadow-sm",
    containerClass
  )}
>
  {#if !src || hasError}
    <div class="bg-muted text-muted-foreground flex h-full w-full items-center justify-center text-[11px] uppercase tracking-[0.18em]">
      {fallbackLabel}
    </div>
  {:else}
    {#if !isLoaded}
      <Skeleton class="absolute inset-0 h-full w-full rounded-none" />
    {/if}

    {#if shouldLoad}
      <img
        {src}
        {alt}
        loading="lazy"
        decoding="async"
        onload={() => {
          isLoaded = true;
        }}
        onerror={() => {
          isLoaded = true;
          hasError = true;
        }}
        class={`h-full w-full object-cover transition-opacity duration-300 ${isLoaded ? "opacity-100" : "opacity-0"} ${imageClass}`}
      />
    {/if}
  {/if}
</div>
