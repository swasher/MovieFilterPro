<script lang="ts">
  import { goto } from "$app/navigation";
  import { Button } from "$lib/components/ui/button";
  import { Badge } from "$lib/components/ui/badge";
  import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "$lib/components/ui/card";
  import { Separator } from "$lib/components/ui/separator";
  import * as Avatar from "$lib/components/ui/avatar";
  import { ArrowLeft } from "@lucide/svelte";

  let { data } = $props();
  const person = $derived(data.person);

  const goBack = async () => {
    if (typeof window === "undefined") return;
    if (window.history.length > 1) {
      window.history.back();
      return;
    }
    await goto("/");
  };

  const initials = (name: string) =>
    name
      .split(" ")
      .map((part) => part[0] ?? "")
      .join("")
      .slice(0, 2)
      .toUpperCase();
</script>

<div class="mx-auto w-full max-w-6xl p-6">
  <div class="mb-5">
    <Button variant="ghost" size="sm" onclick={goBack}>
      <ArrowLeft class="size-4" />
      Back
    </Button>
  </div>

  <div class="grid gap-6 xl:grid-cols-[240px_minmax(0,1fr)]">
    <Card class="overflow-hidden rounded-2xl !gap-0 !py-0">
      <CardContent class="!p-0">
        {#if person.photo_url}
          <img src={person.photo_url} alt={person.name} class="aspect-[3/4] w-full object-cover" />
        {:else}
          <div class="bg-muted flex aspect-[3/4] items-center justify-center">
            <Avatar.Root class="size-28">
              <Avatar.Fallback class="text-2xl">{initials(person.name)}</Avatar.Fallback>
            </Avatar.Root>
          </div>
        {/if}
      </CardContent>
    </Card>

    <div class="space-y-6">
      <Card class="rounded-2xl border-border/70 bg-card/80 shadow-sm">
        <CardHeader class="space-y-4">
          <div class="space-y-1">
            <CardTitle class="text-3xl leading-tight">{person.name}</CardTitle>
            {#if person.original_name && person.original_name !== person.name}
              <CardDescription class="text-base">{person.original_name}</CardDescription>
            {/if}
          </div>

          <div class="flex flex-wrap gap-2">
            <Badge variant="outline">{person.movies_count} films</Badge>
            <Badge variant="outline">{person.roles_count} roles</Badge>
            <Badge variant="outline">{person.career_years} career years</Badge>
            {#if person.country}
              <Badge variant="secondary">{person.country}</Badge>
            {/if}
            {#if person.gender_display}
              <Badge variant="secondary">{person.gender_display}</Badge>
            {/if}
          </div>

          <div class="flex flex-wrap gap-2">
            {#if person.birth_date}
              <Badge variant="outline">born {person.birth_date}</Badge>
            {/if}
            {#if person.death_date}
              <Badge variant="outline">died {person.death_date}</Badge>
            {/if}
            {#if person.actor_count}
              <Badge variant="secondary">actor {person.actor_count}</Badge>
            {/if}
            {#if person.director_count}
              <Badge variant="secondary">director {person.director_count}</Badge>
            {/if}
            {#if person.producer_count}
              <Badge variant="secondary">producer {person.producer_count}</Badge>
            {/if}
          </div>
        </CardHeader>

        {#if person.biography}
          <CardContent>
            <div class="space-y-2">
              <p class="text-muted-foreground text-xs uppercase tracking-[0.18em]">Biography</p>
              <p class="text-sm leading-6">{person.biography}</p>
            </div>
          </CardContent>
        {/if}
      </Card>

      <Card class="rounded-2xl border-border/70 bg-card/80 shadow-sm">
        <CardHeader>
          <CardTitle class="text-xl">Filmography</CardTitle>
        </CardHeader>
        <CardContent class="space-y-4">
          {#if person.filmography.length}
            <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {#each person.filmography as item (`${item.id}-${item.role}-${item.character_name ?? ""}`)}
                <a href={`/movies/${item.slug}`} data-sveltekit-preload-data="hover" class="block">
                  <div class="overflow-hidden rounded-xl border border-border/60 bg-muted/20 transition hover:shadow-md">
                    {#if item.poster_url}
                      <img src={item.poster_url} alt={item.title} class="aspect-[2/3] w-full object-cover" />
                    {:else}
                      <div class="bg-muted text-muted-foreground flex aspect-[2/3] items-center justify-center text-xs">
                        no poster
                      </div>
                    {/if}

                    <div class="space-y-2 p-3">
                      <p class="truncate text-sm font-medium">{item.title}</p>
                      <div class="flex flex-wrap gap-2">
                        {#if item.year}
                          <Badge variant="outline">{item.year}</Badge>
                        {/if}
                        <Badge variant="secondary">{item.role_display}</Badge>
                      </div>
                      {#if item.character_name}
                        <p class="text-muted-foreground truncate text-xs">{item.character_name}</p>
                      {/if}
                    </div>
                  </div>
                </a>
              {/each}
            </div>
          {:else}
            <p class="text-muted-foreground text-sm">No filmography yet.</p>
          {/if}
        </CardContent>
      </Card>
    </div>
  </div>
</div>
