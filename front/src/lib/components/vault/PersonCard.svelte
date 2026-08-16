<script lang="ts">
  import * as Tooltip from "$lib/components/ui/tooltip";
  import { Heart } from "@lucide/svelte";

  type PersonCredit = {
    id: number;
    name: string;
    photo_url: string | null;
    character_name?: string | null;
    is_favorite?: boolean;
  };

  let { person }: { person: PersonCredit } = $props();

  let pointer = $state({ x: 0, y: 0 });

  const cursorAnchor = {
    getBoundingClientRect: () => new DOMRect(pointer.x, pointer.y, 0, 0)
  };

  const initials = (name: string) =>
    name
      .split(" ")
      .map((part) => part[0] ?? "")
      .join("")
      .slice(0, 2)
      .toUpperCase();
</script>

<Tooltip.Root>
  <Tooltip.Trigger>
    {#snippet child({ props })}
      <div role="presentation" class="block" onpointermove={(e) => (pointer = { x: e.clientX, y: e.clientY })}>
        <a {...props} href={`/persons/${person.id}`} data-sveltekit-preload-data="hover" class="block">
          <div class="vd-filmography-card">
            {#if person.photo_url}
              <img src={person.photo_url} alt={person.name} class="vd-photo" />
            {:else}
              <div class="vd-photo-fallback">{initials(person.name)}</div>
            {/if}
            <div class="vd-crew-copy {person.is_favorite ? "vd-crew-copy--favorite" : ""}">
              <div class="vd-crew-title-row">
                {#if person.is_favorite}
                  <Heart class="size-3 shrink-0 fill-red-500 text-red-500" />
                {/if}
                <p class="vd-crew-title">{person.name}</p>
              </div>
              {#if person.character_name}
                <p class="vd-crew-subtitle">{person.character_name}</p>
              {/if}
            </div>
          </div>
        </a>
      </div>
    {/snippet}
  </Tooltip.Trigger>
  <Tooltip.Content
    side="bottom"
    align="center"
    sideOffset={12}
    customAnchor={cursorAnchor}
    updatePositionStrategy="always"
    arrowClasses="hidden"
    class="vd-tooltip"
  >
    <span class="block">{person.name}</span>
    {#if person.character_name}
      <span class="block text-foreground/70">{person.character_name}</span>
    {/if}
  </Tooltip.Content>
</Tooltip.Root>