<script lang="ts">
  import * as Tooltip from "$lib/components/ui/tooltip";
  import MovieStatusBadges from "$lib/components/vault/MovieStatusBadges.svelte";

  type Part = {
    tmdb_id: number;
    title: string;
    original_title: string | null;
    year: number | null;
    poster_url: string | null;
    in_vault: boolean;
    vault_slug: string | null;
    watch_status: "watched" | "will_watch" | "wont_watch" | null;
    rating: number | null;
    is_favorite: boolean;
  };

  let {
    part,
    isCurrent = false,
    isImporting = false,
    onclick
  }: {
    part: Part;
    isCurrent?: boolean;
    isImporting?: boolean;
    onclick?: (part: Part) => void;
  } = $props();

  let pointer = $state({ x: 0, y: 0 });

  const cursorAnchor = {
    getBoundingClientRect: () => new DOMRect(pointer.x, pointer.y, 0, 0)
  };

  const handleClick = () => {
    if (isCurrent) return;
    onclick?.(part);
  };
</script>

<Tooltip.Provider>
  <Tooltip.Root>
    <Tooltip.Trigger>
      {#snippet child({ props })}
        <div
          role="presentation"
          class="block"
          onpointermove={(e) => (pointer = { x: e.clientX, y: e.clientY })}
        >
          {#if part.in_vault && part.vault_slug}
            <a
              {...props}
              href={isCurrent ? undefined : `/movies/${part.vault_slug}`}
              class="vd-collection-card vd-collection-card--compact group"
              aria-current={isCurrent ? "page" : undefined}
              onclick={isCurrent ? (e) => e.preventDefault() : undefined}
              data-sveltekit-preload-data="hover"
            >
              <div class="vd-collection-poster-wrap vd-collection-poster-wrap--compact">
                {#if part.poster_url}
                  <img src={part.poster_url} alt={part.title} class="vd-collection-poster" loading="lazy" />
                {:else}
                  <div class="vd-collection-poster-fallback text-[10px]">no poster</div>
                {/if}
                <MovieStatusBadges
                  watch_status={part.watch_status}
                  rating={part.rating}
                  is_favorite={part.is_favorite}
                />
              </div>
            </a>
          {:else}
            <button
              {...props}
              type="button"
              class="vd-collection-card vd-collection-card--compact vd-collection-card--missing group"
              onclick={handleClick}
              disabled={isImporting}
            >
              <div class="vd-collection-poster-wrap vd-collection-poster-wrap--compact">
                {#if part.poster_url}
                  <img src={part.poster_url} alt={part.title} class="vd-collection-poster vd-collection-poster--dim group-hover:opacity-100 group-hover:grayscale-0" loading="lazy" />
                {:else}
                  <div class="vd-collection-poster-fallback text-[10px]">no poster</div>
                {/if}
                {#if isImporting}
                  <span class="vd-collection-badge vd-collection-badge--loading">Импорт…</span>
                {/if}
              </div>
            </button>
          {/if}
        </div>
      {/snippet}
    </Tooltip.Trigger>
    <Tooltip.Content
      side="top"
      align="center"
      sideOffset={10}
      customAnchor={cursorAnchor}
      updatePositionStrategy="always"
      arrowClasses="hidden"
      class="vd-tooltip vd-collection-tooltip max-w-[240px] border border-border shadow-lg"
    >
      <div class="space-y-1">
        <p class="text-sm font-semibold leading-tight text-foreground">{part.title}</p>
        {#if part.original_title && part.original_title !== part.title}
          <p class="text-xs leading-tight text-muted-foreground">{part.original_title}</p>
        {/if}
        <p class="flex items-center gap-1.5 text-xs text-muted-foreground">
          {#if part.year}
            <span>{part.year}</span>
            <span class="opacity-40">•</span>
          {/if}
          {#if isCurrent}
            <span class="font-medium text-emerald-500">Текущий фильм</span>
          {:else if part.in_vault}
            <span class="text-emerald-600 dark:text-emerald-400">В Vault</span>
          {:else}
            <span>Нет в Vault</span>
          {/if}
        </p>
        {#if !isCurrent && !part.in_vault}
          <p class="text-[11px] leading-tight text-muted-foreground/70">клик — добавить из TMDB</p>
        {/if}
      </div>
    </Tooltip.Content>
  </Tooltip.Root>
</Tooltip.Provider>
