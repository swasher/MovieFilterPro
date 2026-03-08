<script lang="ts">
  import type { Snippet } from "svelte";
  import type { SidebarItem } from "$lib/template-data";
  import { Badge } from "$lib/components/ui/badge";
  import * as Sidebar from "$lib/components/ui/sidebar";

  type Props = {
    children?: Snippet;
    sidebarItems: SidebarItem[];
  };

  let { children, sidebarItems }: Props = $props();

  const isActive = (href: string): boolean => {
    if (typeof window === "undefined") return false;
    const current = `${window.location.pathname}${window.location.search}`;
    return current === href || (href !== "/" && current.startsWith(href));
  };
</script>

<Sidebar.Provider>
  <div class="flex min-h-0 flex-1">
    <Sidebar.Root>
      <Sidebar.Header>
        <div class="px-2 py-3">
          <p class="text-sm font-semibold">Vault</p>
          <p class="text-muted-foreground text-xs">Навигация по фильмотеке</p>
        </div>
      </Sidebar.Header>

      <Sidebar.Content>
        <Sidebar.Group>
          <Sidebar.GroupLabel>Списки</Sidebar.GroupLabel>
          <Sidebar.GroupContent>
            <Sidebar.Menu>
              {#each sidebarItems as item (item.id)}
                <Sidebar.MenuItem>
                  <Sidebar.MenuButton isActive={isActive(item.href)}>
                    {#snippet child({ props })}
                      <a {...props} href={item.href}>
                        <span>{item.title}</span>
                        {#if typeof item.count === "number"}
                          <Badge variant="secondary" class="ml-auto">{item.count}</Badge>
                        {:else if item.children?.length}
                          <Badge variant="secondary" class="ml-auto">{item.children.length}</Badge>
                        {/if}
                      </a>
                    {/snippet}
                  </Sidebar.MenuButton>

                  {#if item.children?.length}
                    <Sidebar.MenuSub>
                      {#each item.children as subItem (subItem.id)}
                        <Sidebar.MenuSubItem>
                          <Sidebar.MenuSubButton isActive={isActive(subItem.href)}>
                            {#snippet child({ props })}
                              <a {...props} href={subItem.href}>
                                <span>{subItem.title}</span>
                                {#if typeof subItem.count === "number"}
                                  <Badge variant="outline" class="ml-auto">{subItem.count}</Badge>
                                {/if}
                              </a>
                            {/snippet}
                          </Sidebar.MenuSubButton>
                        </Sidebar.MenuSubItem>
                      {/each}
                    </Sidebar.MenuSub>
                  {/if}
                </Sidebar.MenuItem>
              {/each}
            </Sidebar.Menu>
          </Sidebar.GroupContent>
        </Sidebar.Group>
      </Sidebar.Content>

      <Sidebar.Rail />
    </Sidebar.Root>

    <Sidebar.Inset class="min-w-0 flex-1">
      <div class="flex min-h-0 flex-1 flex-col">
        <div class="p-4 pb-0 md:hidden">
          <Sidebar.Trigger />
        </div>
        {@render children?.()}
      </div>
    </Sidebar.Inset>
  </div>
</Sidebar.Provider>
