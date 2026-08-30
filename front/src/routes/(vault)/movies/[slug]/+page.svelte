<script lang="ts">
  import { goto, invalidateAll } from "$app/navigation";
  import "../../vault-detail.css";
  import { toast } from "svelte-sonner";
  import { fly } from "svelte/transition";
  import { Button } from "$lib/components/ui/button";
  import { Textarea } from "$lib/components/ui/textarea";
  import { Input } from "$lib/components/ui/input";
  import { Badge } from "$lib/components/ui/badge";
  import { Separator } from "$lib/components/ui/separator";
  import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "$lib/components/ui/card";
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
    Globe,
    Heart,
    Link,
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
  import * as ImageZoom from "$lib/components/ui/image-zoom";
  import SeasonStatus from "$lib/components/vault/SeasonStatus.svelte";
  import PersonCard from "$lib/components/vault/PersonCard.svelte";
  import CollectionPartCard from "$lib/components/vault/CollectionPartCard.svelte";

  let { data } = $props();
  const movie = $derived(data.movie);
  const systemLabels = $derived(data.systemLabels ?? {});
  const wb = $derived(movie.writeback);

  const isSeries = $derived(movie.movie_type === "series" || movie.movie_type === "miniseries");
  const crewCardsRaw = $derived.by(() => {
    if (isSeries) {
      return (movie.showrunners ?? []).slice(0, 3).map((p) => ({ ...p, _roleLabel: "Создатель" }));
    }
    const topDirectors = (movie.directors ?? []).slice(0, 3).map((p) => ({ ...p, _roleLabel: "Режиссер" }));
    const topProducers = (movie.producers ?? []).slice(0, 3).map((p) => ({ ...p, _roleLabel: "Продюсер" }));
    // Screenplay + Writer объединяем в общий пул "Сценарист", топ-3 по popularity
    const writersPool = [...(movie.screenplays ?? []), ...(movie.writers ?? [])]
      .sort((a, b) => (b.popularity ?? 0) - (a.popularity ?? 0))
      .slice(0, 3)
      .map((p) => ({ ...p, _roleLabel: "Сценарист" }));
    return [...topDirectors, ...topProducers, ...writersPool];
  });
  // Дедупликация: один человек — одна карточка, должности объединяем "Режиссер · Продюсер"
  const crewCards = $derived.by(() => {
    const byId = new Map<number, typeof crewCardsRaw[number] & { _roleLabels: string[] }>();
    for (const p of crewCardsRaw) {
      const existing = byId.get(p.id);
      if (!existing) {
        byId.set(p.id, { ...p, _roleLabels: [p._roleLabel] } as typeof byId extends Map<any, infer V> ? V : never);
      } else if (!existing._roleLabels.includes(p._roleLabel)) {
        existing._roleLabels.push(p._roleLabel);
      }
    }
    return Array.from(byId.values()).map((p) => ({
      ...p,
      _roleLabelCombined: p._roleLabels.join(" · ")
    }));
  });
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

  function formatDate(iso: string | null | undefined): string {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    return date.toLocaleDateString("ru-RU");
  }

  function statusDateFor(key: string): string | null {
    switch (key) {
      case "favorites":
        return userState.favorited_at;
      case "watched":
        return userState.watched_at || userState.status_at;
      case "will_watch":
      case "wont_watch":
        return userState.status_at;
      default:
        return null;
    }
  }

  let isSyncing = $state(false);
  let isWritebacking = $state(false);
  let isConfirmingCandidate = $state(false);
  let isDeletingMovie = $state(false);
  let candidateDialogOpen = $state(false);
  let deleteDialogOpen = $state(false);
  let collectionImportDialogOpen = $state(false);
  let pendingCollectionPart = $state<{
    tmdb_id: number;
    title: string;
    original_title: string | null;
    year: number | null;
    poster_url: string | null;
  } | null>(null);
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
    note: "",
    rated_at: null as string | null,
    status_at: null as string | null,
    watched_at: null as string | null,
    note_at: null as string | null,
    favorited_at: null as string | null
  });
  let undoRating = $state<number | null>(null);

  const hasComment = $derived(!!userState.note);
  const canSaveComment = $derived(commentDraft.trim() !== userState.note);
  let seasonsRevision = $state(0);

  const statusButtons = $derived([
    { key: "favorites", label: systemLabels.favorites ?? "Избранное", icon: Heart },
    { key: "will_watch", label: systemLabels.will_watch ?? "Буду смотреть", icon: Bookmark },
    { key: "watched", label: systemLabels.watched ?? "Просмотрено", icon: CheckCheck },
    { key: "wont_watch", label: systemLabels.wont_watch ?? "Не интересует", icon: XCircle }
  ]);

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

  let linkDialogOpen = $state(false);
  let linkTmdbIdInput = $state("");
  let linkCandidates = $state<Array<{
    tmdb_id: number;
    media_type: string;
    title: string;
    original_title: string;
    year: number | null;
    poster_url: string | null;
    popularity: number | null;
    vote_average: number | null;
  }>>([]);
  let selectedLinkCandidateKey = $state<string | null>(null);

  function makeCandidateKey(tmdbId: number, mediaType: string): string {
    return `${tmdbId}-${mediaType}`;
  }
  let isLookingUp = $state(false);
  let linkLookupError = $state("");
  let isLinking = $state(false);
  let linkLookupTimer: ReturnType<typeof setTimeout> | null = null;

  $effect(() => {
    if (linkDialogOpen) {
      linkTmdbIdInput = "";
      linkCandidates = [];
    selectedLinkCandidateKey = null;
      linkLookupError = "";
      isLookingUp = false;
    }
  });

  const runTmdbLookup = async () => {
    const tmdbId = Number(linkTmdbIdInput);
    isLookingUp = true;
    linkLookupError = "";
    linkCandidates = [];

    try {
      // Ищем и movie, и tv параллельно
      const [movieRes, tvRes] = await Promise.all([
        fetch(`/api/vault/tmdb/lookup?tmdb_id=${tmdbId}&media_type=movie`),
        fetch(`/api/vault/tmdb/lookup?tmdb_id=${tmdbId}&media_type=tv`),
      ]);

      const results: Array<{
        tmdb_id: number;
        media_type: string;
        title: string;
        original_title: string;
        year: number | null;
        poster_url: string | null;
        popularity: number | null;
        vote_average: number | null;
      }> = [];

      for (const res of [movieRes, tvRes]) {
        if (res.ok) {
          try {
            const payload = await res.json();
            if (payload.tmdb_id) {
              results.push(payload);
            }
          } catch {
            // игнорируем ошибки парсинга
          }
        }
      }

      if (results.length === 0) {
        // Если оба 404, берем сообщение от movie
        if (!movieRes.ok) {
          const payload = await movieRes.json().catch(() => ({}));
          linkLookupError = payload.message ?? `HTTP ${movieRes.status}`;
        } else if (!tvRes.ok) {
          const payload = await tvRes.json().catch(() => ({}));
          linkLookupError = payload.message ?? `HTTP ${tvRes.status}`;
        } else {
          linkLookupError = "Ничего не найдено на TMDB";
        }
        linkCandidates = [];
      } else {
        linkCandidates = results;
        selectedLinkCandidateKey = results[0] ? makeCandidateKey(results[0].tmdb_id, results[0].media_type) : null;
      }
    } catch (error) {
      linkCandidates = [];
      linkLookupError = error instanceof Error ? error.message : "Не удалось найти фильм на TMDB";
    } finally {
      isLookingUp = false;
    }
  };

  const onLinkIdInput = (event: Event) => {
    linkTmdbIdInput = (event.currentTarget as HTMLInputElement).value;
    if (linkLookupTimer) {
      clearTimeout(linkLookupTimer);
      linkLookupTimer = null;
    }
    linkCandidates = [];
        selectedLinkCandidateKey = null;
    linkLookupError = "";

    const raw = linkTmdbIdInput;
    const tmdbId = Number(raw);
    if (!raw || !Number.isInteger(tmdbId) || tmdbId <= 0) {
      return;
    }

    linkLookupTimer = setTimeout(() => {
      void runTmdbLookup();
    }, 450);
  };

  const linkTmdb = async () => {
    const candidate = linkCandidates.find(c => makeCandidateKey(c.tmdb_id, c.media_type) === selectedLinkCandidateKey);
    if (!candidate) {
      return;
    }

    isLinking = true;

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
        if (await handleUnauthorized(response.status, payload.message)) {
          return;
        }
        toast.error(payload.message ?? `HTTP ${response.status}`);
        return;
      }

      if (payload.status === "ok") {
        linkDialogOpen = false;
        linkTmdbIdInput = "";
        linkCandidates = [];
      selectedLinkCandidateKey = null;
        toast.success(payload.message ?? "TMDB sync done.");
        await invalidateAll();
        return;
      }

      if (payload.status === "needs_confirmation" || payload.status === "needs_user_choice") {
        tmdbCandidates = payload.candidates ?? [];
        selectedCandidateId = tmdbCandidates[0]?.tmdb_id ?? null;
        candidateDialogMode = payload.status;
        linkDialogOpen = false;
        candidateDialogOpen = true;
        toast.warning(payload.message ?? "Нужно подтвердить кандидата.");
        return;
      }

      toast.error(payload.message ?? "TMDB sync failed.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unknown TMDB sync error");
    } finally {
      isLinking = false;
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

  const runWriteback = async () => {
    isWritebacking = true;
    try {
      const res = await fetch(`/api/vault/movies/${movie.slug}/tmdb-writeback`, { method: "POST" });
      const payload = await res.json();
      if (!res.ok) {
        if (await handleUnauthorized(res.status, payload.message)) return;
        toast.error(payload.message ?? `HTTP ${res.status}`);
        return;
      }
      const results = Array.isArray(payload) ? payload : [];
      const ok = results.filter((r) => r.success).length;
      const fail = results.filter((r) => !r.success && r.action !== "skipped").length;
      if (fail) {
        const err = results.find((r) => r.error)?.error ?? "частично";
        toast.warning(`Write-back: ok ${ok}, fail ${fail} — ${err}`);
      } else if (ok) {
        toast.success(`TMDB write-back: ${results.map((r) => r.action).join(", ")}`);
      } else {
        const reason = results[0]?.error ?? "пропущено (нет tmdb_id/токена/выключено)";
        toast.warning(`Write-back пропущен: ${reason}`);
      }
      // обновляем бейдж wb.status (pending/error → synced)
      await invalidateAll();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      isWritebacking = false;
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

  let isImportingCollectionPart = $state(false);
  let importingPartTmdbId = $state<number | null>(null);

  const handleCollectionPartClick = async (part: {
    tmdb_id: number;
    title: string;
    original_title?: string | null;
    year?: number | null;
    poster_url?: string | null;
    in_vault: boolean;
    vault_slug: string | null;
  }) => {
    if (part.in_vault && part.vault_slug) {
      await goto(`/movies/${part.vault_slug}`);
      return;
    }
    // открываем shadcn диалог вместо браузерного confirm
    pendingCollectionPart = {
      tmdb_id: part.tmdb_id,
      title: part.title,
      original_title: part.original_title ?? null,
      year: part.year ?? null,
      poster_url: part.poster_url ?? null
    };
    collectionImportDialogOpen = true;
  };

  const confirmCollectionImport = async () => {
    const part = pendingCollectionPart;
    if (!part) return;
    if (isImportingCollectionPart) return;
    isImportingCollectionPart = true;
    importingPartTmdbId = part.tmdb_id;
    try {
      const response = await fetch("/api/vault/tmdb/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tmdb_id: part.tmdb_id, media_type: "movie" })
      });
      const payload = (await response.json()) as {
        status?: string;
        message?: string;
        movie?: { slug?: string } | null;
      };
      if (!response.ok) {
        if (await handleUnauthorized(response.status, payload.message)) return;
        toast.error(payload.message ?? `HTTP ${response.status}`);
        return;
      }
      const slug = payload.movie?.slug;
      if (!slug) {
        toast.error(payload.message ?? "Не удалось определить фильм после импорта");
        return;
      }
      collectionImportDialogOpen = false;
      pendingCollectionPart = null;
      toast.success(payload.message ?? "Фильм добавлен в Vault");
      await goto(`/movies/${slug}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось импортировать фильм");
    } finally {
      isImportingCollectionPart = false;
      importingPartTmdbId = null;
    }
  };
</script>

<div class="vd-page">
  <div class="vd-layout vd-layout--movie">
    <div class="vd-sidebar">
      <Card class="vd-poster-card !gap-0 !py-0">
        <CardContent class="!p-0">
          {#if movie.poster_url}
            <ImageZoom.Root>
              <ImageZoom.Trigger src={movie.poster_url} alt={movie.title} class="vd-poster" />
            </ImageZoom.Root>
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
                <span class="block">{item.label}</span>
                {#if statusDateFor(item.key)}
                  <span class="block text-foreground/70">с {formatDate(statusDateFor(item.key))}</span>
                {/if}
              </Tooltip.Content>
            </Tooltip.Root>
          </Tooltip.Provider>
        {/each}
      </div>

      <div class="vd-sidebar-stack">
{#if !userState.in_will_watch && !userState.in_wont_watch}
          <div class="vd-rating-row vd-rating-row--sidebar">
            <Tooltip.Root>
              <Tooltip.Trigger>
                <span class="inline-flex items-center gap-1">
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
                </span>
              </Tooltip.Trigger>
              <Tooltip.Content side="bottom" align="center" class="vd-tooltip">
                <span class="block">
                  {#if userState.rating}
                    Оценка: {userState.rating}
                  {:else}
                    Нет оценки
                  {/if}
                </span>
                {#if userState.rated_at}
                  <span class="block text-foreground/70">поставлена {formatDate(userState.rated_at)}</span>
                {/if}
              </Tooltip.Content>
            </Tooltip.Root>

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
              <Button {...props} variant="outline" size="sm" class="w-full justify-between border-dashed font-normal text-muted-foreground hover:text-foreground">
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
              <Tooltip.Root>
                <Tooltip.Trigger class="block w-full">
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
                </Tooltip.Trigger>
                <Tooltip.Content side="bottom" align="center" class="vd-tooltip">
                  <span class="block">{item.label}</span>
                  {#if statusDateFor(item.key)}
                    <span class="block text-foreground/70">с {formatDate(statusDateFor(item.key))}</span>
                  {/if}
                </Tooltip.Content>
              </Tooltip.Root>
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
                <p class="vd-overline">{movie.movie_type === "miniseries" ? "MINISERIES" : "SERIES"}</p>
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
                  {@const tmdbType = movie.tmdb_media_type || (movie.movie_type === 'series' || movie.movie_type === 'miniseries' ? 'tv' : 'movie')}
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
                {#if movie.tvdb_id}
                  <a
                    href="https://www.thetvdb.com/dereferrer/series/{movie.tvdb_id}"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="vd-service-badge vd-service-badge--tvdb"
                    title="Open on TVDB"
                  >
                    TVDB
                  </a>
                {/if}
                {#if movie.homepage}
                  <a
                    href={movie.homepage}
                    target="_blank"
                    rel="noopener noreferrer"
                    class="vd-service-badge vd-service-badge--site"
                    title="Официальный сайт"
                  >
                    <Globe class="size-3" />
                    Site
                  </a>
                {/if}
                {#if movie.trailer_url}
                  <a
                    href={movie.trailer_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    class="vd-service-badge vd-service-badge--site"
                    title="Trailer"
                  >
                    <Link2 class="size-3" />
                    Trailer
                  </a>
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
            {#if (movie.duration || movie.age_rating) && movie.tmdb_original_language}
              <Separator orientation="vertical" class="h-4" />
            {/if}
            {#if movie.tmdb_original_language}
              <span class="vd-fact-inline inline-flex items-center gap-1.5">
                <Globe class="size-3.5" />
                {movie.tmdb_original_language.toUpperCase()}
              </span>
            {/if}
            {#if movie.tmdb_original_language && movie.budget}
              <Separator orientation="vertical" class="h-4" />
            {/if}
            {#if movie.budget}
              <span class="vd-fact-inline inline-flex items-center gap-1.5">
                <Link2 class="size-3.5" />
                ${(movie.budget / 1_000_000).toFixed(1)}M
              </span>
            {/if}
           </div>

          <div class="vd-facts-grid">
            {#if movie.tmdb_vote_average !== null || movie.omdb_imdb_rating !== null || movie.omdb_imdb_votes !== null || movie.omdb_rotten_tomatoes !== null || movie.omdb_metacritic !== null}
              <div class="vd-fact md:col-span-2">
                <dt class="vd-fact-label">Ratings</dt>
                <dd class="vd-fact-value">
                  <div class="flex flex-wrap gap-2">
                    {#if movie.tmdb_vote_average !== null}
                      <span class="vd-omdb-badge vd-omdb-badge--tmdb" title={movie.tmdb_vote_count ? `${movie.tmdb_vote_count} голосов` : undefined}>
                        TMDB {movie.tmdb_vote_average}{#if movie.tmdb_vote_count}<span class="opacity-60">&nbsp;({movie.tmdb_vote_count})</span>{/if}
                      </span>
                    {/if}
                    {#if movie.omdb_imdb_rating !== null}
                      <span class="vd-omdb-badge vd-omdb-badge--imdb" title={movie.omdb_last_synced_at ? `OMDB sync: ${formatDate(movie.omdb_last_synced_at)}` : undefined}>
                        IMDb {movie.omdb_imdb_rating.toFixed(1)}/10{#if movie.omdb_imdb_votes !== null}<span class="opacity-60">&nbsp;({movie.omdb_imdb_votes.toLocaleString('ru-RU')})</span>{/if}
                      </span>
                    {:else if movie.omdb_imdb_votes !== null}
                      <span class="vd-omdb-badge vd-omdb-badge--imdb" title={movie.omdb_last_synced_at ? `OMDB sync: ${formatDate(movie.omdb_last_synced_at)}` : undefined}>
                        IMDb {movie.omdb_imdb_votes.toLocaleString('ru-RU')} голосов
                      </span>
                    {/if}
                    {#if movie.omdb_rotten_tomatoes !== null}
                      <span class="vd-omdb-badge vd-omdb-badge--rt" title={movie.omdb_last_synced_at ? `OMDB sync: ${formatDate(movie.omdb_last_synced_at)}` : undefined}>
                        🍅 {movie.omdb_rotten_tomatoes}%
                      </span>
                    {/if}
                    {#if movie.omdb_metacritic !== null}
                      <span class="vd-omdb-badge vd-omdb-badge--meta" title={movie.omdb_last_synced_at ? `OMDB sync: ${formatDate(movie.omdb_last_synced_at)}` : undefined}>
                        Metacritic {movie.omdb_metacritic}/100
                      </span>
                    {/if}
                  </div>
                </dd>
              </div>
            {/if}
            <div class="vd-fact md:col-span-2">
              <dt class="vd-fact-label">Genres</dt>
              <dd class="vd-fact-value">{compactText(movie.genres)}</dd>
            </div>
            <div class="vd-fact md:col-span-2">
              <dt class="vd-fact-label">Countries</dt>
              <dd class="vd-fact-value">{compactText(movie.countries)}</dd>
            </div>
            {#if movie.keywords.length > 0}
              <div class="vd-fact md:col-span-2">
                <dt class="vd-fact-label">Keywords</dt>
                <dd class="vd-fact-value vd-keywords">
                  {movie.keywords.join(", ")}
                </dd>
              </div>
            {/if}
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

            {#if !hasComment && !isEditingComment}
              <Button
                variant="outline"
                size="sm"
                class="w-fit border-dashed font-normal text-muted-foreground hover:text-foreground"
                onclick={() => {
                  isEditingComment = true;
                }}
              >
                <span class="inline-flex items-center gap-1.5">
                  <Plus class="size-3.5" />
                  Добавить комментарий
                </span>
              </Button>
            {:else}
              <div class="vd-comment-row">
                <Textarea
                  bind:value={commentDraft}
                  bind:ref={commentTextarea}
                  rows={4}
                  disabled={!isEditingComment}
                  placeholder="Ваш комментарий к фильму…"
                  onkeydown={onCommentKeydown}
                  aria-label="Комментарий к фильму"
                  class={hasComment ? "border-2 border-orange-500" : undefined}
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
                            aria-label="Редактировать комментарий"
                          >
                            <Pencil class="size-3.5" />
                          </Button>
                        </Tooltip.Trigger>
                        <Tooltip.Content side="left">Редактировать</Tooltip.Content>
                      </Tooltip.Root>
                    </Tooltip.Provider>

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
                </div>
              </div>
            {/if}
          </div>
      </Card>




      {#if (movie.movie_type === "series" || movie.movie_type === "miniseries") && movie.seasons.length > 0}
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

      {#if movie.collection}
        <Card class="vd-card !gap-2 !py-4">
          <CardHeader class="pb-1 pt-0">
            <CardTitle class="vd-collection-header">{movie.collection.name}</CardTitle>
          </CardHeader>
          <CardContent class="pt-0">
            <div class="vd-collection-grid vd-collection-grid--compact">
              {#each movie.collection.parts as part (part.tmdb_id)}
                <CollectionPartCard
                  {part}
                  isCurrent={part.tmdb_id === movie.tmdb_id}
                  isImporting={isImportingCollectionPart && importingPartTmdbId === part.tmdb_id}
                  onclick={handleCollectionPartClick}
                />
              {/each}
            </div>
          </CardContent>
        </Card>
      {/if}

      <Card class="vd-card">
        <CardContent class="vd-card-content">
          <div class="vd-section">
            <p class="vd-section-title">{isSeries ? "Создатели" : "Crew / Съемочная группа"}</p>
            {#if crewCards.length}
              <div class="vd-crew-grid">
                {#each crewCards as person (person.id)}
                  <PersonCard person={{ ...person, character_name: person._roleLabelCombined }} />
                {/each}
              </div>
            {:else}
              <p class="vd-empty">Нет данных</p>
            {/if}
          </div>

          <div class="vd-section">
            <p class="vd-section-title">В ролях</p>
            <div class="vd-crew-grid">
              {#if movie.actors.length}
                {#each movie.actors as person (person.id)}
                  <PersonCard {person} />
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
            {isSyncing ? "Syncing..." : "Sync using tmdb_id"}
          </Button>
          <Button variant="outline" onclick={() => runTmdbSync(true)} disabled={isSyncing}>
            <RefreshCw class="size-4" />
            Sync and re-match tmdb_id
          </Button>
          <Button variant="outline" onclick={() => { linkDialogOpen = true; }} disabled={isSyncing || isLinking}>
            <Link class="size-4" />
            Link TMDB
          </Button>
          <Button variant="outline" onclick={runWriteback} disabled={isWritebacking || !movie.tmdb_id}>
            <RefreshCw class={`size-4 ${isWritebacking ? "animate-spin" : ""}`} />
            {isWritebacking ? "Pushing..." : "Push to TMDB"}
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
          {#if wb && wb.status !== "synced"}
            {#if wb.status === "error"}
              <Tooltip.Provider>
                <Tooltip.Root>
                  <Tooltip.Trigger>
                    <span class="vd-status-pill border-red-500/20 bg-red-500/10 text-red-700 dark:text-red-300" title={wb.last_error ?? ""}>
                      TMDB error
                    </span>
                  </Tooltip.Trigger>
                  <Tooltip.Content class="max-w-[320px] whitespace-pre-wrap">{wb.last_error ?? wb.reason ?? "Unknown error"}</Tooltip.Content>
                </Tooltip.Root>
              </Tooltip.Provider>
            {:else if wb.status === "pending"}
              <span class="vd-status-pill border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-300" title={wb.last_error ?? ""}>
                Pending{wb.next_retry_at ? ` → ${new Date(wb.next_retry_at).toLocaleTimeString("ru-RU")}` : ""}
              </span>
            {:else if wb.status === "disabled"}
              <span class="vd-status-pill vd-status-pill--secondary" title={wb.reason ?? ""}>Write-back disabled</span>
            {:else if wb.status === "no_tmdb_id"}
              <span class="vd-status-pill vd-status-pill--secondary">No TMDB</span>
            {/if}
          {/if}
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

<Dialog.Root bind:open={linkDialogOpen}>
  <Dialog.Content class="sm:max-w-md">
    <Dialog.Header>
      <Dialog.Title>Привязать к TMDB вручную</Dialog.Title>
      <Dialog.Description>
        Вставь TMDB ID нужного фильма. Название и год подтянутся автоматически.
      </Dialog.Description>
    </Dialog.Header>

    <div class="space-y-3">
      <Input
        type="number"
        placeholder="Например, 550"
        bind:value={linkTmdbIdInput}
        oninput={onLinkIdInput}
        min="1"
      />

      {#if isLookingUp}
        <p class="text-muted-foreground text-sm">Ищем на TMDB…</p>
      {:else if linkLookupError}
        <p class="text-destructive text-sm">{linkLookupError}</p>
      {:else if linkCandidates.length > 0}
        <div class="space-y-2">
          <p class="text-xs text-muted-foreground">Выбери вариант:</p>
          {#each linkCandidates as candidate (candidate.tmdb_id + '-' + candidate.media_type)}
            <button
              type="button"
              class={`w-full rounded-xl border p-3 text-left transition ${selectedLinkCandidateKey === makeCandidateKey(candidate.tmdb_id, candidate.media_type) ? "border-primary bg-accent/40" : "border-border/70 bg-card hover:bg-accent/20"}`}
              onclick={() => { selectedLinkCandidateKey = makeCandidateKey(candidate.tmdb_id, candidate.media_type); }}
            >
              <div class="flex gap-3">
                <div class="bg-muted flex h-[96px] w-16 shrink-0 items-center justify-center overflow-hidden rounded-md relative">
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
                  <span class="absolute top-1 right-1 px-1 py-0.5 text-[9px] font-medium rounded bg-black/60 text-white">
                    {candidate.media_type === 'movie' ? 'movie' : 'tv'}
                  </span>
                </div>
                <div class="min-w-0 flex-1 space-y-1">
                  <div class="space-y-1">
                    <p class="truncate text-sm font-semibold">{candidate.title}</p>
                    {#if candidate.original_title}
                      <p class="text-muted-foreground truncate text-xs">{candidate.original_title}</p>
                    {/if}
                  </div>

                  <div class="flex flex-wrap gap-2">
                    <Badge variant="secondary">{candidate.year ?? "—"}</Badge>
                    <Badge variant="outline">#{candidate.tmdb_id}</Badge>
                    {#if candidate.vote_average}
                      <Badge variant="outline">TMDB {candidate.vote_average.toFixed(1)}</Badge>
                    {/if}
                  </div>
                </div>
              </div>
            </button>
          {/each}
        </div>
      {:else if linkTmdbIdInput}
        <p class="text-muted-foreground text-sm">Введи корректный TMDB ID.</p>
      {/if}
    </div>

    <Dialog.Footer>
      <Button variant="outline" onclick={() => {
        linkDialogOpen = false;
      }} disabled={isLinking}>
        Отмена
      </Button>
      <Button onclick={linkTmdb} disabled={isLinking || selectedLinkCandidateKey === null}>
        {isLinking ? "Сохраняю..." : "OK"}
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

<Dialog.Root bind:open={collectionImportDialogOpen}>
  <Dialog.Content class="sm:max-w-md">
    <Dialog.Header>
      <Dialog.Title>Добавить фильм?</Dialog.Title>
      <Dialog.Description>
        Фильма "{pendingCollectionPart?.title ?? ""}" нет в Vault. Добавить его из TMDB?
      </Dialog.Description>
    </Dialog.Header>

    {#if pendingCollectionPart}
      <div class="flex gap-3 rounded-lg border border-border/50 bg-muted/20 p-3">
        <div class="flex h-[84px] w-14 shrink-0 items-center justify-center overflow-hidden rounded-md bg-muted">
          {#if pendingCollectionPart.poster_url}
            <img src={pendingCollectionPart.poster_url} alt={pendingCollectionPart.title} class="h-full w-full object-cover" loading="lazy" />
          {:else}
            <span class="text-[10px] text-muted-foreground">no poster</span>
          {/if}
        </div>
        <div class="min-w-0 flex-1 space-y-1">
          <p class="truncate text-sm font-semibold">{pendingCollectionPart.title}</p>
          {#if pendingCollectionPart.original_title && pendingCollectionPart.original_title !== pendingCollectionPart.title}
            <p class="truncate text-xs text-muted-foreground">{pendingCollectionPart.original_title}</p>
          {/if}
          {#if pendingCollectionPart.year}
            <p class="text-xs text-muted-foreground">{pendingCollectionPart.year}</p>
          {/if}
          <p class="text-xs text-muted-foreground">TMDB #{pendingCollectionPart.tmdb_id}</p>
        </div>
      </div>
    {/if}

    <Dialog.Footer>
      <Button variant="outline" onclick={() => { collectionImportDialogOpen = false; }} disabled={isImportingCollectionPart}>
        Отмена
      </Button>
      <Button onclick={confirmCollectionImport} disabled={isImportingCollectionPart || !pendingCollectionPart}>
        {isImportingCollectionPart ? "Добавляю..." : "Добавить"}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
