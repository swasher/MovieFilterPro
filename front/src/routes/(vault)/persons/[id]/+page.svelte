<script lang="ts">
  import { goto } from "$app/navigation";
  import "../../vault-detail.css";
  import { Button } from "$lib/components/ui/button";
  import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "$lib/components/ui/card";
  import * as Avatar from "$lib/components/ui/avatar";
  import * as ImageZoom from "$lib/components/ui/image-zoom";
  import { ArrowLeft, Heart, Star } from "@lucide/svelte";
  import PersonFilmography from "$lib/components/vault/PersonFilmography.svelte";
  import VaultImage from "$lib/components/vault/VaultImage.svelte";

  let { data } = $props();
  const person = $derived(data.person);

  const canLoadImages = $derived(!!person.tmdb_id && /^\d+$/.test(person.tmdb_id));
  const hasTmdbLink = $derived(/^\d+$/.test(person.tmdb_id ?? ""));
  const hasImdbLink = $derived(/^nm\d+$/.test(person.imdb_id ?? ""));

  // Фото приходят из +page.ts параллельно с данными персоны.
  const images = $derived(data.images ?? []);
  const imagesError = $derived(data.imagesError ?? "");
  const displayImages = $derived(images.filter((image) => !!image.url || !!image.thumb_url));

  let isFavorite = $state(person.is_favorite);
  let favoriteBusy = $state(false);
  let isStar = $state(person.is_star);
  let starBusy = $state(false);

  const toggleStar = async () => {
    if (starBusy) return;
    starBusy = true;
    try {
      const res = await fetch(`/api/vault/persons/${person.id}/toggle-star`, {
        method: "POST",
      });
      if (res.ok) {
        const result = (await res.json()) as { is_star: boolean };
        isStar = result.is_star;
      }
    } finally {
      starBusy = false;
    }
  };

  const toggleFavorite = async () => {
    if (favoriteBusy) return;
    favoriteBusy = true;
    try {
      const res = await fetch(`/api/vault/persons/${person.id}/toggle-favorite`, {
        method: "POST",
      });
      if (res.ok) {
        const result = (await res.json()) as { is_favorite: boolean };
        isFavorite = result.is_favorite;
      }
    } finally {
      favoriteBusy = false;
    }
  };

  const bioParagraphs = $derived(
    (person.biography ?? "")
      .split(/\n+/)
      .map((p) => p.trim())
      .filter(Boolean)
  );

  const knownForLabels: Record<string, string> = {
    Acting: "Актер",
    Actors: "Актер",
    Directing: "Режиссер",
    Writing: "Сценарист",
    Production: "Продюсер",
    Sound: "Звук",
    Camera: "Оператор",
    Editing: "Монтажер",
    Art: "Художник",
    "Costume & Make-Up": "Костюмы и грим",
    Crew: "Съемочная группа",
    "Visual Effects": "Визуальные эффекты",
    Lighting: "Освещение",
    Creator: "Создатель",
  };

  function formatPersonDate(iso: string | null | undefined): string {
    if (!iso) return "";
    const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
    return match ? `${match[3]}.${match[2]}.${match[1]}` : iso;
  }

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
    <div class="flex w-full flex-col gap-3 self-start">
      <Card class="vd-poster-card !gap-0 !py-0">
        <CardContent class="!p-0">
          {#if person.photo_url}
            <ImageZoom.Root>
              <VaultImage
                src={person.photo_url}
                zoomSrc={person.photo_full_url ?? person.photo_url}
                alt={person.name}
                class="vd-photo"
                slotClass="w-full"
                spinnerClass="size-6"
                fetchpriority="high"
              />
            </ImageZoom.Root>
          {:else}
            <div class="vd-photo-fallback">
              <Avatar.Root class="size-28">
                <Avatar.Fallback class="text-2xl">{initials(person.name)}</Avatar.Fallback>
              </Avatar.Root>
            </div>
          {/if}
        </CardContent>
      </Card>
      <div class="flex w-full flex-col gap-2">
        <Button
          variant={isStar ? "default" : "outline"}
          class={isStar
            ? "w-full bg-amber-400 text-black hover:bg-amber-500"
            : "w-full text-amber-500 hover:bg-amber-500/10"}
          onclick={toggleStar}
          disabled={starBusy}
        >
          <Star class={isStar ? "fill-current" : ""} />
          {isStar ? "In stars" : "Add to stars"}
        </Button>
        <Button
          variant={isFavorite ? "default" : "outline"}
          class={isFavorite
            ? "w-full bg-red-500 text-white hover:bg-red-600"
            : "w-full text-red-500 hover:bg-red-500/10"}
          onclick={toggleFavorite}
        >
          <Heart class={isFavorite ? "fill-current" : ""} />
          {isFavorite ? "In favorites" : "Add to favorites"}
        </Button>
      </div>
    </div>

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

          <div class="vd-facts-row">
            <span class="vd-service-badges">
              {#if hasTmdbLink}
                <a
                  href="https://www.themoviedb.org/person/{person.tmdb_id}"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="vd-service-badge vd-service-badge--tmdb"
                  title="Open on TMDB"
                >
                  TMDB
                </a>
              {:else}
                <span
                  class="vd-service-badge vd-service-badge--empty"
                  title="TMDB ID отсутствует или имеет синтетический формат"
                >
                  empty tmdb id
                </span>
              {/if}
              {#if hasImdbLink}
                <a
                  href="https://www.imdb.com/name/{person.imdb_id}"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="vd-service-badge vd-service-badge--imdb"
                  title="Open on IMDb"
                >
                  IMDb
                </a>
              {:else}
                <span
                  class="vd-service-badge vd-service-badge--empty"
                  title="Реальный IMDb ID отсутствует или имеет синтетический формат"
                >
                  empty imdb id
                </span>
              {/if}
            </span>
          </div>

          <div class="vd-facts-grid">
            <dl class="vd-facts-list">
              {#if person.place_of_birth}
                <div class="vd-fact">
                  <dt class="vd-fact-label">Place of birth</dt>
                  <dd class="vd-fact-value">{person.place_of_birth}</dd>
                </div>
              {/if}
              {#if person.known_for_department}
                <div class="vd-fact">
                  <dt class="vd-fact-label">Known for</dt>
                  <dd class="vd-fact-value" title={person.known_for_department}>
                    {knownForLabels[person.known_for_department] ?? person.known_for_department}
                  </dd>
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
                  <dd class="vd-fact-value" title={person.birth_date}>
                    {formatPersonDate(person.birth_date)}
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
                  <dd class="vd-fact-value" title={person.death_date}>{formatPersonDate(person.death_date)}</dd>
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

          {#if person.also_known_as.length}
            <div class="vd-section">
              <p class="vd-section-title">Also known as</p>
              <div class="vd-tag-stack">
                {#each person.also_known_as as alias (alias)}
                  <span class="vd-chip">{alias}</span>
                {/each}
              </div>
            </div>
          {/if}
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

      {#if canLoadImages && (displayImages.length || imagesError)}
        <Card class="vd-card">
          <CardHeader>
            <CardTitle class="text-xl">Фото персоны</CardTitle>
          </CardHeader>
          <CardContent class="vd-card-content">
            {#if displayImages.length}
              <ImageZoom.Root>
                <div class="vd-person-photos">
                  {#each displayImages as image (image.file_path)}
                    <VaultImage
                      src={image.thumb_url ?? image.url ?? ""}
                      zoomSrc={image.full_url ?? image.url ?? image.thumb_url ?? ""}
                      alt={person.name}
                      class="vd-person-photo"
                      slotClass="vd-person-photo-slot"
                      loading="lazy"
                      decoding="async"
                    />
                  {/each}
                </div>
              </ImageZoom.Root>
            {:else if imagesError}
              <p class="vd-empty">{imagesError}</p>
            {/if}
          </CardContent>
        </Card>
      {/if}

      <PersonFilmography filmography={person.filmography} />
    </div>
  </div>
</div>
