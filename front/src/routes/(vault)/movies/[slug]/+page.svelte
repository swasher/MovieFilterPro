<script lang="ts">
  import { goto, invalidateAll } from "$app/navigation";
  import "../../vault-detail.css";
  import { toast } from "svelte-sonner";
  import { fly } from "svelte/transition";
  import { Button } from "$lib/components/ui/button";
  import { Textarea } from "$lib/components/ui/textarea";
  import { Badge } from "$lib/components/ui/badge";
  import { Separator } from "$lib/components/ui/separator";
  import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "$lib/components/ui/card";
  import * as Avatar from "$lib/components/ui/avatar";
  import * as StarRating from "$lib/components/ui/star-rating";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import * as Dialog from "$lib/components/ui/dialog";
  import {
    Bookmark,
    Check,
    CheckCheck,
    ChevronDown,
    Clock3,
    ExternalLink,
    Heart,
    Link2,
    Pencil,
    Plus,
    RefreshCw,
    Shield,
    Star,
    Trash,
    Trash2,
    X,
    XCircle
  } from "@lucide/svelte";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import SeasonStatus from "$lib/components/vault/SeasonStatus.svelte";

  let { data } = $props();
  const movie = $derived(data.movie);

  const isSeries = $derived(movie.movie_type === "series");
  const isSeriesFinished = $derived(
    isSeries && ["completed", "cancelled"].includes(movie.status)
  );
  const yearLabel = $derived(
    movie.year
      ? isSeries && !isSeriesFinished
        ? `${movie.year} — …`
        : String(movie.year)
      : ""
  );
  const releasedSeasonsCount = $derived(
    movie.seasons.filter((s) => s.season_number > 0 && s.episodes_count > 0).length
  );
  const seasonsLabel = $derived(pluralizeSeasons(releasedSeasonsCount));

  function pluralizeSeasons(n: number): string {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return `${n} сезон`;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} сезона`;
    return `${n} сезонов`;
  }

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
  let isSavingComment = $state(false);
  let isEditingComment = $state(false);
  let commentDraft = $state("");
  let commentTextarea = $state<HTMLTextAreaElement | null>(null);
  let userState = $state({
    in_watched: false,
    in_will_watch: false,
    in_wont_watch: false,
    in_favorites: false,
    rating: null as number | null,
    note: ""
  });
  let undoRating = $state<number | null>(null);

  const hasComment = $derived(!!userState.note);
  const canSaveComment = $derived(commentDraft.trim() !== userState.note);
  let seasonsRevision = $state(0);

  const statusButtons = [
    { key: "favorites", label: "Избранное", icon: Heart },
    { key: "will_watch", label: "Буду смотреть", icon: Bookmark },
    { key: "watched", label: "Просмотрено", icon: CheckCheck },
    { key: "wont_watch", label: "Не буду смотреть", icon: XCircle }
  ] as const;

  $effect(() => {
    userState = { ...movie.user_state };
    customLists = movie.custom_lists.map((item) => ({ ...item }));
    commentDraft = movie.user_state.note;
    isEditingComment = false;
  });

  $effect(() => {
    if (isEditingComment) {
      commentTextarea?.focus();
    }
  });

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
    const prevRating = userState.rating;

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

    if (prevRating !== null && payload.user_state && payload.user_state.rating === null) {
      undoRating = prevRating;
      toast("Рейтинг сброшен при смене статуса", {
        duration: 8000,
        action: {
          label: "Отменить",
          onClick: () => {
            if (undoRating !== null) {
              setRating(undoRating);
              undoRating = null;
            }
          }
        }
      });
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

  const saveComment = async () => {
    isSavingComment = true;

    try {
      const response = await fetch(`/api/vault/movies/${movie.slug}/comment`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: commentDraft.trim() })
      });

      const payload = (await response.json()) as {
        note?: string;
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
      commentDraft = payload.note ?? "";
      isEditingComment = false;
      toast.success("Комментарий сохранён.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось сохранить комментарий");
    } finally {
      isSavingComment = false;
    }
  };

  const cancelCommentEdit = () => {
    commentDraft = userState.note;
    isEditingComment = false;
  };

  const onCommentKeydown = (event: KeyboardEvent) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      if (isEditingComment && canSaveComment && !isSavingComment) {
        void saveComment();
      }
    }
  };

  const clearComment = async () => {
    isSavingComment = true;

    try {
      const response = await fetch(`/api/vault/movies/${movie.slug}/comment`, {
        method: "DELETE"
      });

      const payload = (await response.json()) as {
        note?: string;
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
      commentDraft = "";
      isEditingComment = false;
      toast.success("Комментарий удалён.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось удалить комментарий");
    } finally {
      isSavingComment = false;
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

  const setSeasonStatus = async (season: { id: number; user_state: { watch_status: string | null; rating: number | null } }, watched: boolean) => {
    try {
      const response = await fetch(`/api/vault/seasons/${season.id}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ watch_status: watched ? "watched" : null, rating: null })
      });

      const payload = await response.json();
      if (!response.ok) {
        await handleUnauthorized(response.status, payload.message);
        return;
      }

      season.user_state = { ...payload.user_state };
      seasonsRevision++;
    } catch (error) {
      toast.error("Не удалось обновить статус сезона");
    }
  };

  const setSeasonRating = async (season: { id: number; user_state: { watch_status: string | null; rating: number | null } }, rating: number | null) => {
    try {
      const response = await fetch(`/api/vault/seasons/${season.id}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating: rating })
      });

      const payload = await response.json();
      if (!response.ok) {
        await handleUnauthorized(response.status, payload.message);
        return;
      }

      season.user_state = { ...payload.user_state };
      seasonsRevision++;
    } catch (error) {
      toast.error("Не удалось установить оценку");
    }
  };
</script>

<div class="vd-page">
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

      <div class="vd-status-icons" role="group" aria-label="Статусы фильма">
        {#each statusButtons as item (item.key)}
          {@const Icon = item.icon}
          {@const isActive =
            (item.key === "will_watch" && userState.in_will_watch) ||
            (item.key === "favorites" && userState.in_favorites) ||
            (item.key === "watched" && userState.in_watched) ||
            (item.key === "wont_watch" && userState.in_wont_watch)
          }
          {@const isRated = item.key === "watched" && isActive && !!userState.rating}
          <Tooltip.Provider>
            <Tooltip.Root>
              <Tooltip.Trigger>
                <button
                  type="button"
                  class={`vd-status-icon rounded-full size-10 transition-all duration-200 flex items-center justify-center ${
                    isRated
                      ? "vd-status-icon--active vd-status-icon--rated"
                      : isActive
                        ? "vd-status-icon--active"
                        : "vd-status-icon--inactive"
                  }`}
                  data-status={item.key}
                  onclick={() => toggleStatus(item.key)}
                  aria-pressed={isActive}
                >
                  {#if isRated}
                    <span class="vd-status-icon-rating">{userState.rating}</span>
                  {:else}
                    <Icon class="size-5 transition-colors" />
                  {/if}
                </button>
              </Tooltip.Trigger>
              <Tooltip.Content side="bottom" align="center" class="vd-tooltip">
                {item.label}
              </Tooltip.Content>
            </Tooltip.Root>
          </Tooltip.Provider>
        {/each}
      </div>

      <div class="vd-sidebar-stack">
{#if !userState.in_will_watch && !userState.in_wont_watch}
          <div class="vd-rating-row vd-rating-row--sidebar">
            <StarRating.Root
              value={userState.rating ?? 0}
              max={10}
              class="text-orange-400"
              onValueChange={(value) => setRating(value)}
            >
              {#snippet children({ items })}
                {#each items as item (item.index)}
                  <StarRating.Star index={item.index} state={item.state} class="size-5 vd-star" />
                {/each}
              {/snippet}
            </StarRating.Root>

            {#if userState.rating}
              <button
                type="button"
                class="vd-rating-clear"
                onclick={() => setRating(null)}
                title="Сбросить оценку"
                aria-label="Сбросить оценку"
              >
                <X class="size-3" />
              </button>
            {/if}
          </div>
        {/if}

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
                    onSelect={() => {
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
              <span
                class="vd-list-chip justify-between"
                transition:fly={{ x: 20, duration: 200 }}
              >
                <span class="inline-flex items-center gap-1.5">
                  <span
                    class="size-3.5"
                    class:text-amber-400={item.key === "will_watch"}
                    class:text-red-500={item.key === "favorites" || item.key === "wont_watch"}
                    class:text-emerald-500={item.key === "watched"}
                  >
                    <Icon class="size-3.5" />
                  </span>
                  {item.label}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  class="size-6 p-0 text-muted-foreground/50 hover:bg-muted hover:text-foreground/70"
                  onclick={() => toggleStatus(item.key)}
                  title="Удалить из списка"
                >
                  <Trash class="size-3" />
                </Button>
              </span>
            {/each}

            {#if customLists.some((item) => item.is_in_list)}
              {#each customLists.filter((item) => item.is_in_list) as item (item.id)}
                <div class="vd-list-chip" transition:fly={{ x: 20, duration: 200 }}>
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
      <Card class="vd-card px-6">
          <div class="vd-title-block">
            <div class="flex flex-wrap items-center gap-2">
              {#if isSeries}
                <p class="vd-overline">SERIES</p>
              {:else}
                <p class="vd-overline">Movie</p>
              {/if}
              {#if isSeries}
                <span class="vd-service-badge vd-service-badge--status vd-service-badge--lg">{movie.status_display}</span>
                {#if releasedSeasonsCount > 0}
                  <span class="vd-service-badge vd-service-badge--info vd-service-badge--lg">{seasonsLabel}</span>
                {/if}
              {/if}
              {#if yearLabel}
                <span class="vd-service-badge vd-service-badge--info vd-service-badge--lg">{yearLabel}</span>
              {/if}
              <span class="vd-service-badges ml-auto">
                {#if movie.tmdb_id}
                  {@const tmdbType = movie.tmdb_media_type || (movie.movie_type === 'series' ? 'tv' : 'movie')}
                  <a
                    href="https://www.themoviedb.org/{tmdbType}/{movie.tmdb_id}"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="vd-service-badge vd-service-badge--tmdb"
                    title="Open on TMDB"
                  >
                    TMDB
                  </a>
                {/if}
                {#if movie.imdb_id}
                  <a
                    href="https://www.imdb.com/title/{movie.imdb_id}"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="vd-service-badge vd-service-badge--imdb"
                    title="Open on IMDb"
                  >
                    IMDb
                  </a>
                {/if}
                {#if movie.kinopoisk_id}
                  <a
                    href="https://www.kinopoisk.ru/film/{movie.kinopoisk_id}"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="vd-service-badge vd-service-badge--kinopoisk"
                    title="Open on Kinopoisk"
                  >
                    Кинопоиск
                  </a>
                {/if}
                {#if movie.trailer_url}
                  <Button href={movie.trailer_url} variant="outline" class="vd-segment">
                    <Link2 class="size-4" />
                    Trailer
                  </Button>
                {/if}
              </span>
            </div>
            <CardTitle class="vd-title">{movie.title}</CardTitle>
            {#if movie.original_title}
              <CardDescription class="vd-subtitle">{movie.original_title}</CardDescription>
            {/if}
          </div>

          <div class="vd-facts-row">
            {#if movie.duration}
              <span class="vd-fact-inline inline-flex items-center gap-1.5">
                <Clock3 class="size-3.5" />
                {movie.duration} min
              </span>
            {/if}
            {#if movie.duration && movie.age_rating}
              <Separator orientation="vertical" class="h-4" />
            {/if}
            {#if movie.age_rating}
              <span class="vd-fact-inline inline-flex items-center gap-1.5">
                <Shield class="size-3.5" />
                {movie.age_rating}
              </span>
            {/if}
            {#if movie.age_rating && movie.imdb_rating}
              <Separator orientation="vertical" class="h-4" />
            {/if}
            {#if movie.imdb_rating}
              <span class="vd-fact-inline">IMDb {movie.imdb_rating}</span>
            {/if}
          </div>

          <div class="vd-facts-grid">
            <div class="vd-fact md:col-span-2">
              <dt class="vd-fact-label">Genres</dt>
              <dd class="vd-fact-value">{compactText(movie.genres)}</dd>
            </div>
            <div class="vd-fact md:col-span-2">
              <dt class="vd-fact-label">Countries</dt>
              <dd class="vd-fact-value">{compactText(movie.countries)}</dd>
            </div>
            {#if movie.description}
              <div class="vd-fact md:col-span-2">
                <dt class="vd-fact-label">Plot</dt>
                <dd class="vd-fact-value">{movie.description}</dd>
              </div>
            {/if}
          </div>

          <Separator />

          <div class="vd-section">
            <div class="vd-section-header">
              <p class="vd-section-title">Комментарий</p>
            </div>

            <div class="vd-comment-row">
              <Textarea
                bind:value={commentDraft}
                bind:ref={commentTextarea}
                rows={4}
                disabled={!isEditingComment}
                placeholder="Ваш комментарий к фильму…"
                onkeydown={onCommentKeydown}
                aria-label="Комментарий к фильму"
              />

              <div class="vd-comment-buttons">
                {#if isEditingComment}
                  <Tooltip.Provider>
                    <Tooltip.Root>
                      <Tooltip.Trigger>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onclick={saveComment}
                          disabled={isSavingComment || !canSaveComment}
                          aria-label="Сохранить комментарий"
                        >
                          <Check class="size-3.5" />
                        </Button>
                      </Tooltip.Trigger>
                      <Tooltip.Content side="left">
                        {isSavingComment ? "Сохраняю..." : "Сохранить"}
                      </Tooltip.Content>
                    </Tooltip.Root>
                  </Tooltip.Provider>

                  <Tooltip.Provider>
                    <Tooltip.Root>
                      <Tooltip.Trigger>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onclick={cancelCommentEdit}
                          disabled={isSavingComment}
                          aria-label="Отменить редактирование"
                        >
                          <X class="size-3.5" />
                        </Button>
                      </Tooltip.Trigger>
                      <Tooltip.Content side="left">Отмена</Tooltip.Content>
                    </Tooltip.Root>
                  </Tooltip.Provider>
                {:else}
                  <Tooltip.Provider>
                    <Tooltip.Root>
                      <Tooltip.Trigger>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onclick={() => {
                            isEditingComment = true;
                          }}
                          aria-label={hasComment ? "Редактировать комментарий" : "Добавить комментарий"}
                        >
                          <Pencil class="size-3.5" />
                        </Button>
                      </Tooltip.Trigger>
                      <Tooltip.Content side="left">
                        {hasComment ? "Редактировать" : "Добавить"}
                      </Tooltip.Content>
                    </Tooltip.Root>
                  </Tooltip.Provider>

                  {#if hasComment}
                    <Tooltip.Provider>
                      <Tooltip.Root>
                        <Tooltip.Trigger>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onclick={clearComment}
                            disabled={isSavingComment}
                            aria-label="Удалить комментарий"
                          >
                            <Trash class="size-3.5" />
                          </Button>
                        </Tooltip.Trigger>
                        <Tooltip.Content side="left">Удалить</Tooltip.Content>
                      </Tooltip.Root>
                    </Tooltip.Provider>
                  {/if}
                {/if}
              </div>
            </div>
          </div>
      </Card>




      {#if movie.movie_type === "series" && movie.seasons.length > 0}
        <Card class="vd-card">
          <CardHeader>
            <CardTitle class="text-xl">Сезоны</CardTitle>
          </CardHeader>
          <CardContent class="vd-card-content">
            <div class="vd-season-grid">

              {#each movie.seasons as season (season.id)}
                <div class="vd-card vd-season-card">
                  <div class="vd-season-poster-block">
                    {#if season.poster_url}
                      <img src={season.poster_url} alt={`Постер сезона ${season.season_number}`} class="vd-season-poster-img" />
                    {:else}
                      <div class="vd-season-poster-fallback">no poster</div>
                    {/if}
                    <span class="vd-season-number">{season.season_number}</span>
                  </div>

                  <div class="vd-season-meta">
                    <div class="vd-tag-stack">
                      {#if season.air_year}
                        <span class="vd-chip">{season.air_year}</span>
                      {/if}
                      <span class="vd-chip">{season.episodes_count} серий</span>
                    </div>

                    <SeasonStatus
                      {season}
                      revision={seasonsRevision}
                      onStatusClick={setSeasonStatus}
                      onRatingClick={setSeasonRating}
                    />
                  </div>
                </div>
              {/each}



            </div>
          </CardContent>
        </Card>
      {/if}





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
