<script lang="ts">
  import { page } from "$app/state";
  import type { Snippet } from "svelte";
  import type { SidebarItem } from "$lib/template-data";
  import { defaultSidebarItems } from "$lib/template-data";
  import { Badge } from "$lib/components/ui/badge";
  import { Button } from "$lib/components/ui/button";
  import * as Sidebar from "$lib/components/ui/sidebar";
  import PencilIcon from "@lucide/svelte/icons/pencil";
  import Trash2Icon from "@lucide/svelte/icons/trash-2";
  import PlusIcon from "@lucide/svelte/icons/plus";
  import ListRenameDialog from "$lib/components/ListRenameDialog.svelte";
  import ListDeleteDialog from "$lib/components/ListDeleteDialog.svelte";
  import ListCreateDialog from "$lib/components/ListCreateDialog.svelte";

  type Props = {
    children?: Snippet;
    sidebarItems: SidebarItem[];
  };

  let { children, sidebarItems = $bindable() }: Props = $props();

  let editMode = $state(false);

  // Rename dialog state
  let renameOpen = $state(false);
  let renameListId = $state(0);
  let renameListName = $state("");

  // Delete dialog state
  let deleteOpen = $state(false);
  let deleteListId = $state(0);
  let deleteListName = $state("");

  // Create dialog state
  let createOpen = $state(false);

  const isActive = (href: string): boolean => {
    const currentPath = page.url.pathname;
    const currentSearch = page.url.search;

    if (href.includes("?")) {
      return `${currentPath}${currentSearch}` === href;
    }

    return href === "/" ? currentPath === "/" : currentPath === href || currentPath.startsWith(`${href}/`);
  };

  function isCustomList(id: string): boolean {
    return id.startsWith("list_");
  }

  function getListId(id: string): number {
    return parseInt(id.replace("list_", ""), 10);
  }

  function getCustomGroup(): SidebarItem | undefined {
    return sidebarItems.find((g) => g.id === "custom");
  }

  async function refreshSidebar() {
    try {
      const res = await fetch("/api/vault/sidebar");
      if (!res.ok) return;
      const data = await res.json();
      sidebarItems = data.map((group: any) => ({
        id: group.id,
        title: group.title,
        href: group.href || "#",
        children: group.children.map((item: any) => ({
          id: item.id,
          title: item.title,
          href: item.href,
          count: item.count,
        })),
      }));
    } catch {
      // silently fail
    }
  }

  function openRename(id: number, name: string) {
    renameListId = id;
    renameListName = name;
    renameOpen = true;
  }

  function openDelete(id: number, name: string) {
    deleteListId = id;
    deleteListName = name;
    deleteOpen = true;
  }

  function handleRenameSave(id: number, newName: string) {
    renameOpen = false;
    refreshSidebar();
  }

  function handleRenameCancel() {
    renameOpen = false;
  }

  function handleDeleteConfirm(_id: number) {
    deleteOpen = false;
    refreshSidebar();
  }

  function handleDeleteCancel() {
    deleteOpen = false;
  }

  function handleCreateList(name: string, id: number) {
    createOpen = false;
    refreshSidebar();
  }

  function handleCreateCancel() {
    createOpen = false;
  }

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
                          <div class="flex items-center">
                            <Sidebar.MenuSubButton isActive={isActive(subItem.href)} class="flex-1">
                              {#snippet child({ props })}
                                <a {...props} href={subItem.href}>
                                  <span>{subItem.title}</span>
                                  {#if typeof subItem.count === "number"}
                                    <Badge variant="outline" class="ml-auto">{subItem.count}</Badge>
                                  {/if}
                                </a>
                              {/snippet}
                            </Sidebar.MenuSubButton>

                            {#if editMode && item.id === "custom" && isCustomList(subItem.id)}
                              <div class="ml-1 flex shrink-0 gap-0.5">
                                <button
                                  class="text-muted-foreground hover:text-foreground inline-flex h-5 w-5 items-center justify-center rounded-sm"
                                  title="Переименовать"
                                  onclick={(e) => { e.stopPropagation(); openRename(getListId(subItem.id), subItem.title); }}
                                >
                                  <PencilIcon class="h-3 w-3" />
                                </button>
                                <button
                                  class="text-muted-foreground hover:text-destructive inline-flex h-5 w-5 items-center justify-center rounded-sm"
                                  title="Удалить список"
                                  onclick={(e) => { e.stopPropagation(); openDelete(getListId(subItem.id), subItem.title); }}
                                >
                                  <Trash2Icon class="h-3 w-3" />
                                </button>
                              </div>
                            {/if}
                          </div>
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

      <Sidebar.Footer>
        {#if editMode}
          <div class="flex items-center gap-1 px-2 py-1">
            <Button
              variant="outline"
              size="sm"
              class="h-7 flex-1 text-xs"
              onclick={() => (createOpen = true)}
            >
              <PlusIcon class="mr-1 h-3 w-3" />
              Добавить
            </Button>
            <Button
              variant="secondary"
              size="sm"
              class="h-7 flex-1 text-xs"
              onclick={() => (editMode = false)}
            >
              Готово
            </Button>
          </div>
        {:else}
          <div class="px-2 py-1">
            <Button
              variant="ghost"
              size="sm"
              class="h-7 w-full justify-start text-xs text-muted-foreground"
              onclick={() => (editMode = true)}
            >
              Редактировать
            </Button>
          </div>
        {/if}
      </Sidebar.Footer>

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

<ListRenameDialog
  bind:open={renameOpen}
  listId={renameListId}
  listName={renameListName}
  onsave={handleRenameSave}
  oncancel={handleRenameCancel}
/>

<ListDeleteDialog
  bind:open={deleteOpen}
  listId={deleteListId}
  listName={deleteListName}
  ondelete={handleDeleteConfirm}
  oncancel={handleDeleteCancel}
/>

<ListCreateDialog
  bind:open={createOpen}
  oncreate={handleCreateList}
  oncancel={handleCreateCancel}
/>
