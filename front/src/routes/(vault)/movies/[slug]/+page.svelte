<script lang="ts">
  import { goto, invalidateAll } from "$app/navigation";
  import "../../vault-detail.css";
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import { Badge } from "$lib/components/ui/badge";
  import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "$lib/components/ui/card";
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
    Plus,
    RefreshCw,
    Shield,
    Trash,
    Trash2,
    XCircle
  } from "@lucide/svelte";

  let { data } = $props();
  const movie = $derived(data.movie);

  let isSyncing = $state(false);
  let isConfirmingCandidate = $state(false);
  let isDeletingMovie = $state(false);
  let candidateDialogOpen = $state(false);
  let deleteDialogOpen = $state(false);
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

  const deleteMovie = async () => {
    isDeletingMovie = true;

    try {
      const response = await fetch(`/api/vault/movies/${movie.slug}/delete`, {
        method: "POST"
      });
      const payload = (await response.json()) as {
        message?: string;
        orphan_persons_deleted?: number;
      };

      if (!response.ok) {
        if (await handleUnauthorized(response.status, payload.message)) {
          return;
        }
        toast.error(payload.message ?? `HTTP ${response.status}`);
        return;
      }

      deleteDialogOpen = false;
      if ((payload.orphan_persons_deleted ?? 0) > 0) {
        toast.success(`${payload.message ?? "Фильм удален."} Очищено персон: ${payload.orphan_persons_deleted}.`);
      } else {
        toast.success(payload.message ?? "Фильм удален.");
      }
      await goto("/");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось удалить фильм");
    } finally {
      isDeletingMovie = false;
    }
  };

  const initials = (name: string) =>
    name
      .split(" ")
      .map((part) => part[0] ?? "")
      .join("")
      .slice(0, 2)
      .toUpperCase();

  const compactText = (items: Array<{ name: string }>) => items.map((item) => item.name).join(", ") || "Not set";
</script>

<div class="vd-page">
  <div class="vd-back">
    <Button variant="ghost" size="sm" onclick={goBack}>
      <ArrowLeft class="size-4" />
      Back
    </Button>
  </div>

  <div class="vd-layout vd-layout--movie">
    <div class="vd-sidebar">
      <Card class="vd-poster-card !gap-0 !py-0">
        <CardContent class="!p-0">
          {#if movie.poster_url}
            <img src={movie.poster_url} alt={movie.title} class="vd-poster" />
          {:else}
            <div class="vd-poster-fallback">
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

      <div class="vd-sidebar-stack">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger>
            {#snippet child({ props })}
              <Button {...props} variant="secondary" class="w-full justify-between">
                <span class="inline-flex items-center gap-1.5">
                  <Plus class="size-3.5" />
                  Добавить в список
                </span>
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

        <div class="vd-section">
          <p class="vd-section-title">В списках</p>
          <div class="vd-list-column">
            {#each statusButtons.filter((item) => {
              if (item.key === "will_watch") return userState.in_will_watch;
              if (item.key === "favorites") return userState.in_favorites;
              if (item.key === "watched") return userState.in_watched;
              return userState.in_wont_watch;
            }) as item (item.key)}
              {@const Icon = item.icon}
              <button
                type="button"
                class="vd-list-chip justify-between"
                onclick={() => toggleStatus(item.key)}
              >
                <span class="inline-flex items-center gap-1.5">
                  <Icon class="size-3.5" />
                  {item.label}
                </span>
                <span class="size-1.5 rounded-full bg-primary -translate-x-2"></span>
              </button>
            {/each}

            {#if customLists.some((item) => item.is_in_list)}
              {#each customLists.filter((item) => item.is_in_list) as item (item.id)}
                <div class="vd-list-chip">
                  <span class="flex-1 truncate">{item.name}</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    class="size-6 p-0 text-muted-foreground/50 hover:bg-muted hover:text-foreground/70"
                    onclick={() => toggleCustomList(item.id)}
                    title="Удалить из списка"
                  >
                    <Trash class="size-3" />
                  </Button>
                </div>
              {/each}
            {:else}
              <p class="vd-sidebar-note mt-1">Фильм пока не добавлен в пользовательские списки.</p>
            {/if}
          </div>
        </div>
      </div>
    </div>

    <div class="space-y-5">
      <Card class="vd-card">
        <CardHeader class="vd-hero">
          <div class="vd-title-block">
            <p class="vd-overline">Movie</p>
            <CardTitle class="vd-title">{movie.title}</CardTitle>
            {#if movie.original_title}
              <CardDescription class="vd-subtitle">{movie.original_title}</CardDescription>
            {/if}
          </div>

          <div class="vd-facts-row">
            {#if movie.year}
              <span class="vd-fact-inline">{movie.year}</span>
            {/if}
            <span class="vd-fact-inline">{movie.movie_type_display}</span>
            {#if movie.duration}
              <span class="vd-fact-inline inline-flex items-center gap-1.5">
                <Clock3 class="size-3.5" />
                {movie.duration} min
              </span>
            {/if}
            {#if movie.age_rating}
              <span class="vd-fact-inline inline-flex items-center gap-1.5">
                <Shield class="size-3.5" />
                {movie.age_rating}
              </span>
            {/if}
            {#if movie.imdb_rating}
              <span class="vd-fact-inline">IMDb {movie.imdb_rating}</span>
            {/if}
          </div>

          <div class="vd-facts-grid">
            <dl class="vd-facts-list">
              <div class="vd-fact">
                <dt class="vd-fact-label">Genres</dt>
                <dd class="vd-fact-value">{compactText(movie.genres)}</dd>
              </div>
              <div class="vd-fact">
                <dt class="vd-fact-label">Countries</dt>
                <dd class="vd-fact-value">{compactText(movie.countries)}</dd>
              </div>
            </dl>

            <div class="vd-section">
              <p class="vd-section-title">Статус</p>
              <div class="vd-status-row">
                <span class="vd-status-pill vd-status-pill--primary">{movie.status_display}</span>
              </div>
            </div>
          </div>
        </CardHeader>

        <CardContent class="vd-card-content">
          <div class="vd-section">
            <div class="vd-section-header">
              <p class="vd-section-title">User actions</p>
            </div>
            <div class="vd-primary-actions">
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
                  class="vd-segment"
                  onclick={() => toggleStatus(item.key)}
                >
                  <Icon class="size-4" />
                  {item.label}
                </Button>
              {/each}
            </div>
          </div>

          <div class="vd-section">
            <p class="vd-section-title">Моя оценка</p>
            <div class="vd-rating-row">
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

              <div class="vd-rating-value">{userState.rating ?? 0}/10</div>

              {#if userState.rating}
                <Button variant="ghost" size="sm" onclick={() => setRating(null)}>Clear</Button>
              {/if}
            </div>
          </div>

          {#if movie.description}
            <div class="vd-section">
              <p class="vd-section-title">About</p>
              <p class="vd-copy">{movie.description}</p>
            </div>
          {/if}

          {#if userState.note}
            <div class="vd-section">
              <p class="vd-section-title">Note</p>
              <p class="vd-copy whitespace-pre-wrap">{userState.note}</p>
            </div>
          {/if}
        </CardContent>
      </Card>

      <Card class="vd-card">
        <CardHeader>
          <CardTitle class="text-xl">Съемочная группа</CardTitle>
        </CardHeader>
        <CardContent class="vd-card-content">
          <div class="vd-section">
            <p class="vd-section-title">Режиссеры</p>
            <div class="vd-related-grid">
              {#if movie.directors.length}
                {#each movie.directors as person (person.id)}
                  <a href={`/persons/${person.id}`} data-sveltekit-preload-data="hover" class="block">
                    <div class="vd-related-card">
                      <Avatar.Root class="vd-related-avatar">
                        {#if person.photo_url}
                          <Avatar.Image src={person.photo_url} alt={person.name} class="object-cover" />
                        {/if}
                        <Avatar.Fallback>{initials(person.name)}</Avatar.Fallback>
                      </Avatar.Root>
                      <div class="vd-related-copy">
                        <p class="vd-related-title">{person.name}</p>
                      </div>
                    </div>
                  </a>
                {/each}
              {:else}
                <p class="vd-empty">Нет данных</p>
              {/if}
            </div>
          </div>

          <div class="vd-section">
            <p class="vd-section-title">В ролях</p>
            <div class="vd-related-grid">
              {#if movie.actors.length}
                {#each movie.actors as person (person.id)}
                  <a href={`/persons/${person.id}`} data-sveltekit-preload-data="hover" class="block">
                    <div class="vd-related-card">
                      <Avatar.Root class="vd-related-avatar">
                        {#if person.photo_url}
                          <Avatar.Image src={person.photo_url} alt={person.name} class="object-cover" />
                        {/if}
                        <Avatar.Fallback>{initials(person.name)}</Avatar.Fallback>
                      </Avatar.Root>
                      <div class="vd-related-copy">
                        <p class="vd-related-title">{person.name}</p>
                        {#if person.character_name}
                          <p class="vd-related-subtitle">{person.character_name}</p>
                        {/if}
                      </div>
                    </div>
                  </a>
                {/each}
              {:else}
                <p class="vd-empty">Нет данных</p>
              {/if}
            </div>
          </div>

        </CardContent>
      </Card>

      <div class="vd-service-row">
        <div class="vd-service-actions">
          <Button onclick={() => runTmdbSync(false)} disabled={isSyncing}>
            {isSyncing ? "Sync..." : "Fetch"}
          </Button>
          <Button variant="outline" onclick={() => runTmdbSync(true)} disabled={isSyncing}>
            <RefreshCw class="size-4" />
            Force data
          </Button>
          <Button variant="destructive" onclick={() => {
            deleteDialogOpen = true;
          }} disabled={isDeletingMovie}>
            <Trash2 class="size-4" />
            Delete
          </Button>
        </div>

        <div class="vd-status-row vd-status-row--service">
          <span class={`vd-status-pill ${movie.tmdb_linked ? "vd-status-pill--success" : "vd-status-pill--secondary"}`}>
            {movie.tmdb_linked ? `TMDB linked #${movie.tmdb_id}` : "TMDB not linked"}
          </span>
          <span class="vd-status-pill vd-status-pill--secondary">source: {movie.source_display}</span>
        </div>
      </div>
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

<Dialog.Root bind:open={deleteDialogOpen}>
  <Dialog.Content class="sm:max-w-md">
    <Dialog.Header>
      <Dialog.Title>Удалить фильм?</Dialog.Title>
      <Dialog.Description>
        Это удалит <strong>{movie.title}</strong> из Vault вместе со связанными пользовательскими статусами и списками.
      </Dialog.Description>
    </Dialog.Header>

    <Dialog.Footer>
      <Button variant="outline" onclick={() => {
        deleteDialogOpen = false;
      }} disabled={isDeletingMovie}>
        Отмена
      </Button>
      <Button variant="destructive" onclick={deleteMovie} disabled={isDeletingMovie}>
        {isDeletingMovie ? "Удаляю..." : "Удалить"}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
