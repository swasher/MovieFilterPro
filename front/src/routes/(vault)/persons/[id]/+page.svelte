<script lang="ts">
  import { goto } from "$app/navigation";
  import "../../vault-detail.css";
  import { Button } from "$lib/components/ui/button";
  import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "$lib/components/ui/card";
  import * as Avatar from "$lib/components/ui/avatar";
  import { ArrowLeft } from "@lucide/svelte";

  let { data } = $props();
  const person = $derived(data.person);

  const bioParagraphs = $derived(
    (person.biography ?? "")
      .split(/\n+/)
      .map((p) => p.trim())
      .filter(Boolean)
  );

  const personAge = $derived.by(() => {
    if (!person.birth_date) return null;
    const birth = new Date(person.birth_date);
    if (isNaN(birth.getTime())) return null;
    const end = person.death_date ? new Date(person.death_date) : new Date();
    if (isNaN(end.getTime())) return null;
    let age = end.getFullYear() - birth.getFullYear();
    const beforeBirthday = end.getMonth() < birth.getMonth() ||
      (end.getMonth() === birth.getMonth() && end.getDate() < birth.getDate());
    if (beforeBirthday) age--;
    return age;
  });

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

<div class="vd-page">
  <div class="vd-back">
    <Button variant="ghost" size="sm" onclick={goBack}>
      <ArrowLeft class="size-4" />
      Back
    </Button>
  </div>

  <div class="vd-layout vd-layout--person">
    <Card class="vd-poster-card !gap-0 !py-0 self-start">
      <CardContent class="!p-0">
        {#if person.photo_url}
          <img src={person.photo_url} alt={person.name} class="vd-photo" />
        {:else}
          <div class="vd-photo-fallback">
            <Avatar.Root class="size-28">
              <Avatar.Fallback class="text-2xl">{initials(person.name)}</Avatar.Fallback>
            </Avatar.Root>
          </div>
        {/if}
      </CardContent>
    </Card>

    <div class="space-y-5">
      <Card class="vd-card">
        <CardHeader class="vd-hero">
          <div class="vd-title-block">
            <p class="vd-overline">Person</p>
            <CardTitle class="vd-title">{person.name}</CardTitle>
            {#if person.original_name && person.original_name !== person.name}
              <CardDescription class="vd-subtitle">{person.original_name}</CardDescription>
            {/if}
          </div>

          <div class="vd-facts-row">
            <span class="vd-fact-inline">{person.movies_count} films</span>
            <span class="vd-fact-inline">{person.roles_count} roles</span>
            <span class="vd-fact-inline">{person.career_years} career years</span>
          </div>

          <div class="vd-facts-grid">
            <dl class="vd-facts-list">
              {#if person.country}
                <div class="vd-fact">
                  <dt class="vd-fact-label">Country</dt>
                  <dd class="vd-fact-value">{person.country}</dd>
                </div>
              {/if}
              {#if person.gender_display}
                <div class="vd-fact">
                  <dt class="vd-fact-label">Gender</dt>
                  <dd class="vd-fact-value">{person.gender_display}</dd>
                </div>
              {/if}
              {#if person.birth_date}
                <div class="vd-fact">
                  <dt class="vd-fact-label">Born</dt>
                  <dd class="vd-fact-value">
                    {person.birth_date}
                    {#if personAge !== null}
                      <span class="text-muted-foreground">
                        · {personAge} {person.death_date ? "at death" : "years old"}
                      </span>
                    {/if}
                  </dd>
                </div>
              {/if}
              {#if person.death_date}
                <div class="vd-fact">
                  <dt class="vd-fact-label">Died</dt>
                  <dd class="vd-fact-value">{person.death_date}</dd>
                </div>
              {/if}
            </dl>

            <div class="vd-section">
              <p class="vd-section-title">Основные роли</p>
              <div class="vd-tag-stack">
                {#if person.actor_count}
                  <span class="vd-chip">actor {person.actor_count}</span>
                {/if}
                {#if person.director_count}
                  <span class="vd-chip">director {person.director_count}</span>
                {/if}
                {#if person.producer_count}
                  <span class="vd-chip">producer {person.producer_count}</span>
                {/if}
              </div>
            </div>
          </div>
        </CardHeader>

        {#if bioParagraphs.length}
          <CardContent class="vd-card-content">
            <div class="vd-section">
              <p class="vd-section-title">Biography</p>
              {#each bioParagraphs as paragraph}
                <p class="vd-copy">{paragraph}</p>
              {/each}
            </div>
          </CardContent>
        {/if}
      </Card>

      <Card class="vd-card">
        <CardHeader>
          <CardTitle class="text-xl">Filmography</CardTitle>
        </CardHeader>
        <CardContent class="vd-card-content">
          {#if person.filmography.length}
            <div class="vd-filmography-grid">
              {#each person.filmography as item (`${item.id}`)}
                <a href={`/movies/${item.slug}`} data-sveltekit-preload-data="hover" class="block">
                  <div class="vd-filmography-card">
                    {#if item.poster_url}
                      <img src={item.poster_url} alt={item.title} class="vd-poster" />
                    {:else}
                      <div class="vd-poster-fallback">
                        no poster
                      </div>
                    {/if}

                    <div class="vd-filmography-copy">
                      <p class="vd-related-title">{item.title}</p>
                      <div class="vd-facts-row vd-facts-row--muted">
                        {#if item.year}
                          <span class="vd-fact-inline">{item.year}</span>
                        {/if}
                        <span class="vd-fact-inline">{item.roles.join(", ")}</span>
                      </div>
                      {#if item.character_names.length}
                        <p class="vd-related-subtitle">{item.character_names.join(", ")}</p>
                      {/if}
                    </div>
                  </div>
                </a>
              {/each}
            </div>
          {:else}
            <p class="vd-empty">No filmography yet.</p>
          {/if}
        </CardContent>
      </Card>
    </div>
  </div>
</div>
