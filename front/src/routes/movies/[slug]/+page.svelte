<script lang="ts">
  import { goto, invalidateAll } from "$app/navigation";
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import { Badge } from "$lib/components/ui/badge";
  import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "$lib/components/ui/card";
  import { Separator } from "$lib/components/ui/separator";
  import * as Avatar from "$lib/components/ui/avatar";
  import * as StarRating from "$lib/components/ui/star-rating";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import * as Dialog from "$lib/components/ui/dialog";
  import {
    ArrowLeft,
    Bookmark,
    CheckCheck,
    ChevronDown,
    Clock3,
    Heart,
    Link2,
    RefreshCw,
    Shield,
    XCircle
  } from "@lucide/svelte";

  let { data } = $props();
  const movie = $derived(data.movie);

  let isSyncing = $state(false);
  let isConfirmingCandidate = $state(false);
  let candidateDialogOpen = $state(false);
  let candidateDialogMode = $state<"needs_confirmation" | "needs_user_choice">("needs_user_choice");
  let tmdbCandidates = $state<
    Array<{
      tmdb_id: number;
      media_type: string;
      title: string;
      original_title: string;
      year: number | null;
      score: number;
      score_reasons: string[];
      poster_url: string | null;
      popularity: number | null;
      vote_average: number | null;
    }>
  >([]);
  let selectedCandidateId = $state<number | null>(null);
  let customLists = $state<
    Array<{
      id: number;
      name: string;
      is_public: boolean;
      is_in_list: boolean;
    }>
  >([]);
  let pendingListIds = $state<number[]>([]);
  let userState = $state({
    in_watched: false,
    in_will_watch: false,
    in_wont_watch: false,
    in_favorites: false,
    rating: null as number | null,
    note: ""
  });

  const statusButtons = [
    { key: "will_watch", label: "Буду смотреть", icon: Bookmark },
    { key: "favorites", label: "Избранное", icon: Heart },
    { key: "watched", label: "Просмотрено", icon: CheckCheck },
    { key: "wont_watch", label: "Не буду смотреть", icon: XCircle }
  ] as const;

  $effect(() => {
    userState = { ...movie.user_state };
    customLists = movie.custom_lists.map((item) => ({ ...item }));
  });

  const goBack = async () => {
    if (typeof window === "undefined") return;
    if (window.history.length > 1) {
      window.history.back();
      return;
    }
    await goto("/");
  };

  const handleUnauthorized = async (status: number, message?: string) => {
    if (status !== 401) {
      return false;
    }

    toast.error(message ?? "Нужно войти в систему.");
    await goto("/login");
    return true;
  };

  const runTmdbSync = async (forceRematch: boolean) => {
    isSyncing = true;

    try {
      const response = await fetch(`/api/vault/movies/${movie.slug}/fetch-tmdb`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force_rematch: forceRematch })
      });

      const payload = (await response.json()) as {
        status?: "ok" | "error" | "needs_confirmation" | "needs_user_choice";
        message?: string;
        updated_fields?: string[];
        candidates?: Array<{
          tmdb_id: number;
          media_type: string;
          title: string;
          original_title: string;
          year: number | null;
          score: number;
          score_reasons: string[];
          poster_url: string | null;
          popularity: number | null;
          vote_average: number | null;
        }>;
      };

      if (!response.ok) {
        if (await handleUnauthorized(response.status, payload.message)) {
          return;
        }
        toast.error(payload.message ?? `HTTP ${response.status}`);
        return;
      }

      if (payload.status === "ok") {
        toast.success(payload.message ?? "TMDB sync done.");
      } else if (payload.status === "needs_confirmation" || payload.status === "needs_user_choice") {
        tmdbCandidates = payload.candidates ?? [];
        selectedCandidateId = tmdbCandidates[0]?.tmdb_id ?? null;
        candidateDialogMode = payload.status;
        candidateDialogOpen = true;
        toast.warning(payload.message ?? "TMDB requires manual confirmation.");
      } else {
        toast.error(payload.message ?? "TMDB sync failed.");
      }

      if (payload.status === "ok") {
        await invalidateAll();
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unknown TMDB sync error");
    } finally {
      isSyncing = false;
    }
  };

  const confirmTmdbCandidate = async () => {
    const candidate = tmdbCandidates.find((item) => item.tmdb_id === selectedCandidateId);
    if (!candidate) {
      toast.error("Выбери кандидата.");
      return;
    }

    isConfirmingCandidate = true;

    try {
      const response = await fetch(`/api/vault/movies/${movie.slug}/fetch-tmdb-confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tmdb_id: candidate.tmdb_id,
          media_type: candidate.media_type
        })
      });

      const payload = (await response.json()) as {
        status?: "ok" | "error" | "needs_confirmation" | "needs_user_choice";
        message?: string;
        candidates?: typeof tmdbCandidates;
      };

      if (!response.ok) {
        toast.error(payload.message ?? `HTTP ${response.status}`);
        return;
      }

      if (payload.status === "ok") {
        candidateDialogOpen = false;
        tmdbCandidates = [];
        selectedCandidateId = null;
        toast.success(payload.message ?? "TMDB sync done.");
        await invalidateAll();
        return;
      }

      if (payload.status === "needs_confirmation" || payload.status === "needs_user_choice") {
        tmdbCandidates = payload.candidates ?? [];
        selectedCandidateId = tmdbCandidates[0]?.tmdb_id ?? null;
        candidateDialogMode = payload.status;
        toast.warning(payload.message ?? "Нужно подтвердить кандидата.");
        return;
      }

      toast.error(payload.message ?? "TMDB sync failed.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unknown TMDB confirm error");
    } finally {
      isConfirmingCandidate = false;
    }
  };

  const toggleStatus = async (statusKey: (typeof statusButtons)[number]["key"]) => {
    const response = await fetch(`/api/vault/movies/${movie.slug}/toggle-status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status_key: statusKey })
    });

    const payload = (await response.json()) as {
      user_state?: typeof userState;
      message?: string;
    };

    if (!response.ok) {
      if (await handleUnauthorized(response.status, payload.message)) {
        return;
      }
      toast.error(payload.message ?? `HTTP ${response.status}`);
      return;
    }

    if (payload.user_state) {
      userState = { ...payload.user_state };
    }
  };

  const setRating = async (ratingValue: number | null) => {
    const response = await fetch(`/api/vault/movies/${movie.slug}/rate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating: ratingValue })
    });

    const payload = (await response.json()) as {
      user_state?: typeof userState;
      message?: string;
    };

    if (!response.ok) {
      if (await handleUnauthorized(response.status, payload.message)) {
        return;
      }
      toast.error(payload.message ?? `HTTP ${response.status}`);
      return;
    }

    if (payload.user_state) {
      userState = { ...payload.user_state };
    }
  };

  const toggleCustomList = async (listId: number) => {
    if (pendingListIds.includes(listId)) {
      return;
    }

    pendingListIds = [...pendingListIds, listId];

    const response = await fetch(`/api/vault/movies/${movie.slug}/toggle-list`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ list_id: listId })
    });

    const payload = (await response.json()) as {
      custom_lists?: typeof customLists;
      message?: string;
    };

    pendingListIds = pendingListIds.filter((id) => id !== listId);

    if (!response.ok) {
      if (await handleUnauthorized(response.status, payload.message)) {
        return;
      }
      toast.error(payload.message ?? `HTTP ${response.status}`);
      return;
    }

    if (payload.custom_lists) {
      customLists = payload.custom_lists.map((item) => ({ ...item }));
    }
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

  <div class="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)]">
    <div class="space-y-4">
      <Card class="overflow-hidden rounded-xl !gap-0 !py-0">
        <CardContent class="!p-0">
          {#if movie.poster_url}
            <img src={movie.poster_url} alt={movie.title} class="aspect-[2/3] w-full object-cover" />
          {:else}
            <div class="bg-muted text-muted-foreground flex aspect-[2/3] items-center justify-center text-sm">
              no poster
            </div>
          {/if}
        </CardContent>
      </Card>

      {#if movie.trailer_url}
        <Button href={movie.trailer_url} variant="outline" class="w-full">
          <Link2 class="size-4" />
          Trailer
        </Button>
      {/if}

      <div class="space-y-3">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger>
            {#snippet child({ props })}
              <Button {...props} variant="outline" class="w-full justify-between">
                <span>Добавить в список</span>
                <ChevronDown class="size-4" />
              </Button>
            {/snippet}
          </DropdownMenu.Trigger>
          <DropdownMenu.Content class="w-64 p-1" align="start">
            <DropdownMenu.Group>
              {#if customLists.length}
                {#each customLists as item (item.id)}
                  <DropdownMenu.CheckboxItem
                    class="py-1"
                    checked={item.is_in_list}
                    disabled={pendingListIds.includes(item.id)}
                    onSelect={(event) => {
                      event.preventDefault();
                      void toggleCustomList(item.id);
                    }}
                  >
                    {item.name}
                  </DropdownMenu.CheckboxItem>
                {/each}
              {:else}
                <DropdownMenu.Item disabled>Списков пока нет</DropdownMenu.Item>
              {/if}
            </DropdownMenu.Group>
          </DropdownMenu.Content>
        </DropdownMenu.Root>

        <div class="space-y-2">
          <p class="text-muted-foreground text-xs uppercase tracking-[0.18em]">В списках</p>
          {#if customLists.some((item) => item.is_in_list)}
            <div class="flex flex-col items-start gap-2">
              {#each customLists.filter((item) => item.is_in_list) as item (item.id)}
                <Badge variant="secondary" class="w-full justify-start rounded-md px-3 py-1.5">
                  {item.name}
                </Badge>
              {/each}
            </div>
          {:else}
            <p class="text-muted-foreground text-sm">Фильм пока не добавлен в пользовательские списки.</p>
          {/if}
        </div>
      </div>
    </div>

    <div class="space-y-6">
      <Card class="rounded-2xl border-border/70 bg-card/80 shadow-sm">
        <CardHeader class="space-y-4">
          <div class="space-y-1">
            <CardTitle class="text-3xl leading-tight">{movie.title}</CardTitle>
            {#if movie.original_title}
              <CardDescription class="text-base">{movie.original_title}</CardDescription>
            {/if}
          </div>

          <div class="flex flex-wrap gap-2">
            <Badge variant={movie.tmdb_linked ? "default" : "secondary"}>
              {movie.tmdb_linked ? `TMDB linked #${movie.tmdb_id}` : "TMDB not linked"}
            </Badge>
            <Badge variant="outline">source: {movie.source_display}</Badge>
            {#if movie.imdb_rating}
              <Badge variant="secondary">{movie.imdb_rating} rating</Badge>
            {/if}
            {#if movie.year}
              <Badge variant="outline">{movie.year} year</Badge>
            {/if}
            <Badge variant="outline">{movie.movie_type_display}</Badge>
            {#if movie.duration}
              <Badge variant="outline">
                <Clock3 class="size-3.5" />
                {movie.duration} min
              </Badge>
            {/if}
            {#if movie.age_rating}
              <Badge variant="outline">
                <Shield class="size-3.5" />
                {movie.age_rating}
              </Badge>
            {/if}
          </div>

          <div class="space-y-3">
            <div class="flex flex-wrap items-center gap-2">
              <span class="text-muted-foreground text-sm">Genres:</span>
              {#if movie.genres.length}
                {#each movie.genres as genre (genre.slug ?? genre.name)}
                  <Badge variant="secondary">{genre.name}</Badge>
                {/each}
              {:else}
                <span class="text-muted-foreground text-sm">Not set</span>
              {/if}
            </div>

            <div class="flex flex-wrap items-center gap-2">
              <span class="text-muted-foreground text-sm">Countries:</span>
              {#if movie.countries.length}
                {#each movie.countries as country (country.name)}
                  <Badge variant="outline">{country.name}</Badge>
                {/each}
              {:else}
                <span class="text-muted-foreground text-sm">Not set</span>
              {/if}
            </div>

            <div class="flex flex-wrap items-center gap-2">
              <span class="text-muted-foreground text-sm">Status:</span>
              <Badge variant="outline">{movie.status_display}</Badge>
            </div>
          </div>
        </CardHeader>

        <CardContent class="space-y-5">
          <div class="flex flex-wrap gap-2">
            <Button onclick={() => runTmdbSync(false)} disabled={isSyncing}>
              {isSyncing ? "Sync..." : "Fetch"}
            </Button>
            <Button variant="outline" onclick={() => runTmdbSync(true)} disabled={isSyncing}>
              <RefreshCw class="size-4" />
              Force data
            </Button>
          </div>

          <Separator />

          <div class="space-y-3">
            <p class="text-muted-foreground text-xs uppercase tracking-[0.18em]">User actions</p>
            <div class="flex flex-wrap gap-2">
              {#each statusButtons as item (item.key)}
                {@const Icon = item.icon}
                <Button
                  variant={
                    (item.key === "will_watch" && userState.in_will_watch) ||
                    (item.key === "favorites" && userState.in_favorites) ||
                    (item.key === "watched" && userState.in_watched) ||
                    (item.key === "wont_watch" && userState.in_wont_watch)
                      ? "default"
                      : "outline"
                  }
                  size="sm"
                  onclick={() => toggleStatus(item.key)}
                >
                  <Icon class="size-4" />
                  {item.label}
                </Button>
              {/each}
            </div>
          </div>

          <div class="space-y-3">
            <p class="text-muted-foreground text-xs uppercase tracking-[0.18em]">Rating</p>

            <div class="flex flex-wrap items-center gap-3">
              <StarRating.Root
                value={userState.rating ?? 0}
                max={10}
                class="text-amber-500"
                onValueChange={(value) => setRating(value)}
              >
                {#snippet children({ items })}
                  {#each items as item (item.index)}
                    <StarRating.Star index={item.index} state={item.state} class="size-7" />
                  {/each}
                {/snippet}
              </StarRating.Root>

              <Badge
                variant="secondary"
                class="bg-orange-400 px-3 py-1 text-base font-semibold text-black"
              >
                {userState.rating ?? 0}
              </Badge>

              {#if userState.rating}
                <Button variant="ghost" size="sm" onclick={() => setRating(null)}>Clear</Button>
              {/if}
            </div>
          </div>

          {#if movie.description}
            <div class="space-y-2">
              <p class="text-muted-foreground text-xs uppercase tracking-[0.18em]">About</p>
              <p class="text-sm leading-6">{movie.description}</p>
            </div>
          {/if}

          {#if userState.note}
            <div class="space-y-2">
              <p class="text-muted-foreground text-xs uppercase tracking-[0.18em]">Note</p>
              <p class="text-sm leading-6 whitespace-pre-wrap">{userState.note}</p>
            </div>
          {/if}
        </CardContent>
      </Card>

      <Card class="rounded-2xl border-border/70 bg-card/80 shadow-sm">
        <CardHeader>
          <CardTitle class="text-xl">Съемочная группа</CardTitle>
        </CardHeader>
        <CardContent class="space-y-6">
          <div class="space-y-3">
            <p class="text-muted-foreground text-xs uppercase tracking-[0.18em]">Режиссеры</p>
            <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {#if movie.directors.length}
                {#each movie.directors as person (person.id)}
                  <a href={`/persons/${person.id}`} data-sveltekit-preload-data="hover" class="block">
                    <div class="flex items-center gap-3 rounded-xl border border-border/60 bg-muted/30 p-3 transition hover:shadow-sm">
                      <Avatar.Root class="size-14">
                        {#if person.photo_url}
                          <Avatar.Image src={person.photo_url} alt={person.name} class="object-cover" />
                        {/if}
                        <Avatar.Fallback>{initials(person.name)}</Avatar.Fallback>
                      </Avatar.Root>
                      <div class="min-w-0">
                        <p class="truncate text-sm font-medium">{person.name}</p>
                      </div>
                    </div>
                  </a>
                {/each}
              {:else}
                <p class="text-muted-foreground text-sm">Нет данных</p>
              {/if}
            </div>
          </div>

          <Separator />

          <div class="space-y-3">
            <p class="text-muted-foreground text-xs uppercase tracking-[0.18em]">В ролях</p>
            <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {#if movie.actors.length}
                {#each movie.actors as person (person.id)}
                  <a href={`/persons/${person.id}`} data-sveltekit-preload-data="hover" class="block">
                    <div class="flex items-center gap-3 rounded-xl border border-border/60 bg-muted/30 p-3 transition hover:shadow-sm">
                      <Avatar.Root class="size-14">
                        {#if person.photo_url}
                          <Avatar.Image src={person.photo_url} alt={person.name} class="object-cover" />
                        {/if}
                        <Avatar.Fallback>{initials(person.name)}</Avatar.Fallback>
                      </Avatar.Root>
                      <div class="min-w-0">
                        <p class="truncate text-sm font-medium">{person.name}</p>
                        {#if person.character_name}
                          <p class="text-muted-foreground truncate text-xs">{person.character_name}</p>
                        {/if}
                      </div>
                    </div>
                  </a>
                {/each}
              {:else}
                <p class="text-muted-foreground text-sm">Нет данных</p>
              {/if}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  </div>
</div>

<Dialog.Root bind:open={candidateDialogOpen}>
  <Dialog.Content class="sm:max-w-3xl">
    <Dialog.Header>
      <Dialog.Title>
        {candidateDialogMode === "needs_confirmation" ? "Подтверждение TMDB-совпадения" : "Выбор фильма на TMDB"}
      </Dialog.Title>
      <Dialog.Description>
        {#if candidateDialogMode === "needs_confirmation"}
          Найден один неуверенный кандидат. Проверь его и подтверди выбор вручную.
        {:else}
          Найдено несколько кандидатов. Выбери нужный вариант и подтверди.
        {/if}
      </Dialog.Description>
    </Dialog.Header>

    <div class="max-h-[65vh] space-y-3 overflow-y-auto pr-1">
      {#each tmdbCandidates as candidate (candidate.tmdb_id)}
        <button
          type="button"
          class={`w-full rounded-xl border p-3 text-left transition ${
            selectedCandidateId === candidate.tmdb_id
              ? "border-primary bg-accent/40"
              : "border-border/70 bg-card hover:bg-accent/20"
          }`}
          onclick={() => {
            selectedCandidateId = candidate.tmdb_id;
          }}
        >
          <div class="flex gap-3">
            <div class="bg-muted flex h-[96px] w-16 shrink-0 items-center justify-center overflow-hidden rounded-md">
              {#if candidate.poster_url}
                <img
                  src={candidate.poster_url}
                  alt={candidate.title}
                  class="h-full w-full object-cover"
                  loading="lazy"
                />
              {:else}
                <span class="text-muted-foreground text-[10px]">no poster</span>
              {/if}
            </div>

            <div class="min-w-0 flex-1 space-y-2">
              <div class="space-y-1">
                <p class="truncate text-sm font-semibold">{candidate.title}</p>
                {#if candidate.original_title}
                  <p class="text-muted-foreground truncate text-xs">{candidate.original_title}</p>
                {/if}
              </div>

              <div class="flex flex-wrap gap-2">
                <Badge variant="secondary">{candidate.media_type}</Badge>
                <Badge variant="outline">{candidate.year ?? "—"}</Badge>
                <Badge variant="outline">score {candidate.score}</Badge>
                {#if candidate.vote_average}
                  <Badge variant="outline">TMDB {candidate.vote_average.toFixed(1)}</Badge>
                {/if}
              </div>

              {#if candidate.score_reasons.length}
                <p class="text-muted-foreground line-clamp-2 text-xs">
                  {candidate.score_reasons.join(", ")}
                </p>
              {/if}
            </div>
          </div>
        </button>
      {/each}
    </div>

    <Dialog.Footer>
      <Button variant="outline" onclick={() => {
        candidateDialogOpen = false;
      }}>
        Отмена
      </Button>
      <Button onclick={confirmTmdbCandidate} disabled={isConfirmingCandidate || selectedCandidateId === null}>
        {isConfirmingCandidate ? "Сохраняю..." : "Выбрать"}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
