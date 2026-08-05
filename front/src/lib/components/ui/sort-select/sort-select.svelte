<script lang="ts">
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import { Button } from "$lib/components/ui/button";
  import { Separator } from "$lib/components/ui/separator";
  import { ArrowDownWideNarrow, ArrowUpWideNarrow } from "@lucide/svelte";

  let { value, onChange }: { value: string; onChange: (value: string) => void } = $props();

  const orderOptions = [
    { field: "year", label: "По году" },
    { field: "imdb_rating", label: "По рейтингу" },
    { field: "title", label: "По названию" },
    { field: "added_at", label: "По дате добавления" }
  ];

  const getOrderField = (v: string) => v.replace(/^-/, "");
  const getOrderDirection = (v: string) => (v.startsWith("-") ? "desc" : "asc");
  const buildOrderValue = (field: string, direction: "asc" | "desc") =>
    direction === "desc" ? `-${field}` : field;

  const activeOrderField = $derived(getOrderField(value || "-year"));
  const activeOrderDirection = $derived(getOrderDirection(value || "-year"));

  function onFieldChange(field: string) {
    onChange(buildOrderValue(field, activeOrderDirection));
  }

  function toggleDirection() {
    const next = activeOrderDirection === "desc" ? "asc" : "desc";
    onChange(buildOrderValue(activeOrderField, next));
  }
</script>

<div class="flex items-center rounded-md border border-input overflow-hidden">
  <DropdownMenu.Root>
    <DropdownMenu.Trigger>
      {#snippet child({ props })}
        <Button {...props} variant="ghost" class="border-0 rounded-none h-11 focus:ring-0 shadow-none px-3">
          {orderOptions.find((item) => item.field === activeOrderField)?.label ?? "Сортировка"}
        </Button>
      {/snippet}
    </DropdownMenu.Trigger>
    <DropdownMenu.Content align="end">
      <DropdownMenu.RadioGroup
        value={activeOrderField}
        onValueChange={onFieldChange}
      >
        {#each orderOptions as item (item.field)}
          <DropdownMenu.RadioItem value={item.field}>
            {item.label}
          </DropdownMenu.RadioItem>
        {/each}
      </DropdownMenu.RadioGroup>
    </DropdownMenu.Content>
  </DropdownMenu.Root>

  <Separator orientation="vertical" class="h-5" />

  <Button
    variant="ghost"
    size="icon"
    class="rounded-none h-11 w-11"
    onclick={toggleDirection}
  >
    {#if activeOrderDirection === "desc"}
      <ArrowDownWideNarrow class="h-4 w-4" />
    {:else}
      <ArrowUpWideNarrow class="h-4 w-4" />
    {/if}
  </Button>
</div>
