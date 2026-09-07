<script lang="ts">
  import { untrack } from "svelte";
  import { toast } from "svelte-sonner";
  import { goto } from "$app/navigation";
  import { Button } from "$lib/components/ui/button";
  import { Badge } from "$lib/components/ui/badge";
  import { Input } from "$lib/components/ui/input";
  import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle
  } from "$lib/components/ui/card";
  import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow
  } from "$lib/components/ui/table";
  import * as Dialog from "$lib/components/ui/dialog";
  import * as HoverCard from "$lib/components/ui/hover-card/index.js";
  import * as Tooltip from "$lib/components/ui/tooltip";
  import { CheckCheck, ExternalLink, Play, Plus, RefreshCw, RotateCw, Square, Trash2 } from "@lucide/svelte";
  import * as Pagination from "$lib/components/ui/pagination";

  let { data } = $props();

  const PAGE_SIZE = 100;

  type QueueItem = {
    id: number;
    movie_id: number;
    movie_slug: string;
    movie_title: string;
    movie_original_title: string;
    movie_year: number | null;
    movie_description: string;
    movie_poster_url: string | null;
    movie_has_tmdb: boolean;
    snapshot_title: string;
    snapshot_original_title: string;
    snapshot_year: number | null;
    state: string;
    queued_at: string;
    started_at: string | null;
    finished_at: string | null;
    result_status: string;
    result_title: string;
    result_original_title: string;
    result_year: number | null;
    result_tmdb_id: number | null;
    result_media_type: string;
    result_message: string;
    retry_count: number;
  };

  type TmdbCandidate = {
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
    overview: string;
  };

  type QueueState = {
    enabled: boolean;
    counters: Record<string, number>;
    total_unsynced: number;
    missing_keys?: string[];
  };

  const KEY_LABELS: Record<string, string> = {
    tmdb_api_key: "TMDB API key",
    omdb_api_key: "OMDB API key"
  };
  const keyLabel = (key: string) => KEY_LABELS[key] ?? key;

  let enabled = $state(data.state?.enabled ?? false);
  let counters = $state<Record<string, number>>(data.state?.counters ?? {});
  let totalUnsynced = $state(data.state?.total_unsynced ?? 0);
  let missingKeys = $state<string[]>(data.state?.missing_keys ?? []);
  let items = $state<QueueItem[]>(data.items ?? []);
  let total = $state(data.total ?? 0);
  let page = $state(data.page ?? 1);
  let apiError = $state(data.apiError);
  let jumpTo = $state("");

  let isAdding = $state(false);
  let isStarting = $state(false);
  let isStopping = $state(false);
  let isRemoving = $state(false);
  let isRemovingSynced = $state(false);
  let removeDialogOpen = $state(false);
  let resyncDialogOpen = $state(false);
  let isResyncing = $state(false);
  let deletingIds = $state<Record<number, boolean>>({});
  let syncingIds = $state<Record<number, boolean>>({});
  let candidateDialogOpen = $state(false);
  let candidateDialogMode = $state<"needs_confirmation" | "needs_user_choice">("needs_user_choice");
  let tmdbCandidates = $state<TmdbCandidate[]>([]);
  let selectedCandidateId = $state<number | null>(null);
  let isConfirmingCandidate = $state(false);
  let activeSyncItem = $state<QueueItem | null>(null);

  const handleUnauthorized = async (status: number, message?: string): Promise<boolean> => {
    if (status !== 401) return false;
    toast.error(message ?? "Нужно войти в систему.");
    await goto("/login");
    return true;
  };

  // Лёгкий опрос состояния (без тяжёлого items+count) — для авто-таймера.
  // Полный refresh (state + items) — только по ручным действиям;
  // смена страницы идёт через навигацию с ?page= (данные подтягивает load).
  const refreshState = async () => {
    const stateResponse = await fetch("/api/vault/tmdb-sync/state");

    if (stateResponse.ok) {
      const payload = (await stateResponse.json()) as QueueState;
      enabled = payload.enabled;
      counters = payload.counters;
      totalUnsynced = payload.total_unsynced;
      missingKeys = payload.missing_keys ?? [];
    } else if (stateResponse.status === 401) {
      await handleUnauthorized(401);
    }
  };

  const refreshItems = async () => {
    const itemsResponse = await fetch(
      `/api/vault/tmdb-sync/items?limit=${PAGE_SIZE}&offset=${(page - 1) * PAGE_SIZE}`
    );

    if (itemsResponse.ok) {
      const payload = (await itemsResponse.json()) as {
        items: QueueItem[];
        total: number;
      };
      items = payload.items.map((item) => ({ ...item }));
      total = payload.total;
    }
  };

  const refresh = async () => {
    const stateResponse = await fetch("/api/vault/tmdb-sync/state");

    if (stateResponse.ok) {
      const payload = (await stateResponse.json()) as QueueState;
      enabled = payload.enabled;
      counters = payload.counters;
      totalUnsynced = payload.total_unsynced;
      missingKeys = payload.missing_keys ?? [];
    } else if (stateResponse.status === 401) {
      await handleUnauthorized(401);
      return;
    }

    await refreshItems();

    // Очередь могла ужаться (удаления/обработка): уводим с несуществующей страницы.
    // Навигацию и дозагрузку выполнит вотчер page ниже.
    const maxPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
    if (page > maxPage) {
      page = maxPage;
    }
  };

  // Polling: пауза на скрытой вкладке, чаще при активной обработке.
  // Таймер дёргает только state (дешёвый запрос без count/offset);
  // список items обновляется при смене страницы и ручных действиях.
  $effect(() => {
    const intervalMs = enabled ? 5000 : 10000;
    let timer: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      if (timer) return;
      timer = setInterval(refreshState, intervalMs);
    };
    const stop = () => {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    };
    const onVisibility = () => {
      if (document.hidden) stop();
      else start();
    };

    start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  });

  // Навигация (goto с ?page=) обновляет data через load — подхватываем в локальный стейт.
  $effect(() => {
    page = data.page ?? 1;
    items = data.items ?? [];
    total = data.total ?? 0;
    enabled = data.state?.enabled ?? enabled;
    counters = data.state?.counters ?? {};
    totalUnsynced = data.state?.total_unsynced ?? totalUnsynced;
    missingKeys = data.state?.missing_keys ?? missingKeys;
  });

  // Смена страницы пагинации — навигация с ?page= в URL (переживает reload, шарится ссылкой).
  // Данные подтянет load через goto, ручной refreshItems здесь не нужен.
  $effect(() => {
    const current = page;
    const loaded = untrack(() => data.page ?? 1);
    if (current === loaded) return;
    const params = untrack(() => new URLSearchParams(window.location.search));
    if (current <= 1) params.delete("page");
    else params.set("page", String(current));
    const query = params.toString();
    const target = `/tmdb-sync${query ? `?${query}` : ""}`;
    const currentUrl = untrack(() => window.location.pathname + window.location.search);
    if (currentUrl === target) return;
    void goto(target, { replaceState: true, keepFocus: true, noScroll: true });
  });

  // ?page= вышел за пределы (очередь ужалась или вручную ввели 999) — на последнюю страницу.
  $effect(() => {
    if (total > 0 && page > totalPages) {
      page = totalPages;
    }
  });

  const addAll = async () => {
    isAdding = true;
    try {
      const response = await fetch("/api/vault/tmdb-sync/queue", { method: "POST" });
      const payload = (await response.json()) as { added?: number; total?: number; detail?: string };
      if (!response.ok) {
        if (await handleUnauthorized(response.status, payload.detail)) return;
        toast.error(payload.detail ?? `HTTP ${response.status}`);
        return;
      }
      toast.success(`Добавлено в очередь: ${payload.added}. Всего записей: ${payload.total}.`);
      await refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось добавить фильмы в очередь");
    } finally {
      isAdding = false;
    }
  };

  const resyncAll = async () => {
    if (isResyncing) return;
    isResyncing = true;
    try {
      const response = await fetch("/api/vault/tmdb-sync/resync", { method: "POST" });
      const payload = (await response.json()) as {
        added?: number;
        removed?: number;
        total?: number;
        detail?: string;
      };
      if (!response.ok) {
        if (await handleUnauthorized(response.status, payload.detail)) return;
        toast.error(payload.detail ?? `HTTP ${response.status}`);
        return;
      }
      resyncDialogOpen = false;
      toast.success(
        `Re-Sync: удалено готовых ${payload.removed ?? 0}, добавлено в начало очереди ${payload.added}.`
      );
      await refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось выполнить Re-Sync");
    } finally {
      isResyncing = false;
    }
  };

  const startProcessing = async () => {
    isStarting = true;
    try {
      const response = await fetch("/api/vault/tmdb-sync/start", { method: "POST" });
      if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
          const payload = (await response.json()) as { detail?: string };
          if (payload.detail?.trim()) detail = payload.detail.trim();
        } catch {
          // ignore non-json payloads
        }
        if (await handleUnauthorized(response.status, detail)) return;
        toast.error(detail);
        await refreshState();
        return;
      }
      toast.success("Обработка очереди запущена.");
      await refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось запустить обработку");
    } finally {
      isStarting = false;
    }
  };

  const stopProcessing = async () => {
    isStopping = true;
    try {
      const response = await fetch("/api/vault/tmdb-sync/stop", { method: "POST" });
      if (!response.ok) {
        if (await handleUnauthorized(response.status)) return;
        toast.error(`HTTP ${response.status}`);
        return;
      }
      toast.success("Обработка остановлена (текущий фильм доработает).");
      await refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось остановить обработку");
    } finally {
      isStopping = false;
    }
  };

  const removeAll = async () => {
    isRemoving = true;
    try {
      const response = await fetch("/api/vault/tmdb-sync/queue", { method: "DELETE" });
      const payload = (await response.json()) as { deleted?: number; detail?: string };
      if (!response.ok) {
        if (await handleUnauthorized(response.status, payload.detail)) return;
        toast.error(payload.detail ?? `HTTP ${response.status}`);
        return;
      }
      removeDialogOpen = false;
      toast.success(`Очередь очищена: удалено ${payload.deleted ?? 0} записей.`);
      await refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось очистить очередь");
    } finally {
      isRemoving = false;
    }
  };

  const deleteItem = async (item: QueueItem) => {
    if (deletingIds[item.id]) return;
    deletingIds = { ...deletingIds, [item.id]: true };
    try {
      const response = await fetch(`/api/vault/tmdb-sync/items/${item.id}`, { method: "DELETE" });
      const payload = (await response.json()) as { deleted?: number; detail?: string };
      if (!response.ok) {
        if (await handleUnauthorized(response.status, payload.detail)) return;
        toast.error(payload.detail ?? `HTTP ${response.status}`);
        return;
      }
      items = items.filter((entry) => entry.id !== item.id);
      total = Math.max(0, total - 1);
      if (items.length === 0 && page > 1) {
        page -= 1;
      }
      toast.success(`Запись «${item.snapshot_title}» удалена из очереди.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось удалить запись из очереди");
    } finally {
      deletingIds = { ...deletingIds, [item.id]: false };
    }
  };

  const syncOne = async (item: QueueItem) => {
    if (!item.movie_slug || syncingIds[item.id]) return;
    syncingIds = { ...syncingIds, [item.id]: true };
    try {
      const response = await fetch(`/api/vault/movies/${item.movie_slug}/fetch-tmdb`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force_rematch: false })
      });
      const payload = (await response.json()) as {
        status?: "ok" | "error" | "needs_confirmation" | "needs_user_choice";
        message?: string;
        detail?: string;
        candidates?: TmdbCandidate[];
      };
      if (!response.ok) {
        if (await handleUnauthorized(response.status, payload.message ?? payload.detail)) return;
        toast.error(payload.message ?? payload.detail ?? `HTTP ${response.status}`);
        return;
      }
      if (payload.status === "ok") {
        toast.success(payload.message ?? "TMDB sync done.");
        await refresh();
      } else if (payload.status === "needs_confirmation" || payload.status === "needs_user_choice") {
        tmdbCandidates = payload.candidates ?? [];
        selectedCandidateId = tmdbCandidates[0]?.tmdb_id ?? null;
        candidateDialogMode = payload.status;
        activeSyncItem = { ...item };
        candidateDialogOpen = true;
        toast.warning(payload.message ?? "TMDB requires manual confirmation.");
      } else {
        toast.error(payload.message ?? "TMDB sync failed.");
        await refresh();
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось синхронизировать фильм");
    } finally {
      syncingIds = { ...syncingIds, [item.id]: false };
    }
  };

  const confirmTmdbCandidate = async () => {
    const candidate = tmdbCandidates.find((entry) => entry.tmdb_id === selectedCandidateId);
    if (!candidate) {
      toast.error("Выбери кандидата.");
      return;
    }
    if (!activeSyncItem?.movie_slug) {
      toast.error("Нет фильма для подтверждения.");
      return;
    }
    if (isConfirmingCandidate) return;
    isConfirmingCandidate = true;
    try {
      const response = await fetch(`/api/vault/movies/${activeSyncItem.movie_slug}/fetch-tmdb-confirm`, {
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
        detail?: string;
        candidates?: TmdbCandidate[];
      };
      if (!response.ok) {
        if (await handleUnauthorized(response.status, payload.message ?? payload.detail)) return;
        toast.error(payload.message ?? payload.detail ?? `HTTP ${response.status}`);
        return;
      }
      if (payload.status === "ok") {
        candidateDialogOpen = false;
        tmdbCandidates = [];
        selectedCandidateId = null;
        activeSyncItem = null;
        toast.success(payload.message ?? "TMDB sync done.");
        await refresh();
        return;
      }
      if (payload.status === "needs_confirmation" || payload.status === "needs_user_choice") {
        tmdbCandidates = payload.candidates ?? [];
        selectedCandidateId = tmdbCandidates[0]?.tmdb_id ?? null;
        candidateDialogMode = payload.status;
        toast.warning(payload.message ?? "Нужно подтвердить кандидата.");
        return;
      }
      toast.error(payload.message ?? payload.detail ?? "TMDB sync failed.");
      await refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unknown TMDB confirm error");
    } finally {
      isConfirmingCandidate = false;
    }
  };

  const removeSynced = async () => {
    if (isRemovingSynced) return;
    isRemovingSynced = true;
    try {
      const response = await fetch("/api/vault/tmdb-sync/queue/synced", { method: "DELETE" });
      const payload = (await response.json()) as { deleted?: number; detail?: string };
      if (!response.ok) {
        if (await handleUnauthorized(response.status, payload.detail)) return;
        toast.error(payload.detail ?? `HTTP ${response.status}`);
        return;
      }
      toast.success(`Удалено готовых: ${payload.deleted ?? 0}.`);
      await refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось удалить готовые записи");
    } finally {
      isRemovingSynced = false;
    }
  };



  const stateLabels: Record<string, string> = {
    pending: "В очереди",
    in_progress: "Обрабатывается",
    synced: "Синхронизирован",
    confirm: "Нужен выбор",
    not_found: "Не найден",
    error: "Ошибка"
  };

  const stateBadgeClass = (state: string) => {
    if (state === "synced") return "text-emerald-700 border-emerald-600/40 dark:text-emerald-400";
    if (state === "error") return "";
    if (state === "not_found") return "text-amber-700 border-amber-600/40 dark:text-amber-400";
    if (state === "in_progress") return "animate-pulse";
    return "";
  };

  const stateBadgeVariant = (state: string) => {
    if (state === "error") return "destructive" as const;
    if (state === "synced" || state === "not_found") return "outline" as const;
    return "secondary" as const;
  };

  const formatDateTime = (iso: string | null) =>
    iso ? new Date(iso).toLocaleString() : "";

  const queuedCount = $derived(counters.pending ?? 0);
  const totalPages = $derived(Math.max(1, Math.ceil(total / PAGE_SIZE)));
  const rangeStart = $derived(total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1);
  const rangeEnd = $derived(Math.min(total, page * PAGE_SIZE));

  const submitJump = (event: SubmitEvent) => {
    event.preventDefault();
    const next = Math.floor(Number(jumpTo));
    if (!Number.isFinite(next)) return;
    jumpTo = "";
    page = Math.min(Math.max(1, next), totalPages);
  };

  const isProcessing = $derived(enabled && (counters.in_progress ?? 0) > 0);
  const statusLabel = $derived(
    enabled
      ? queuedCount > 0
        ? isProcessing
          ? "Идёт обработка…"
          : "В очереди…"
        : "Очередь пуста"
      : "Остановлено"
  );
</script>

<div class="mx-auto flex w-full max-w-[1400px] flex-col gap-4 p-4">
  <Card>
    <CardHeader>
      <CardTitle class="text-lg">TMDB Sync Queue</CardTitle>
      <CardDescription>
        Массовая синхронизация фильмотеки с TMDB: 1 фильм за проход. Очередь:
        {counters.pending ?? 0} записей из {totalUnsynced} несинхронизированных.
        Скорость ограничена лимитером TMDB (2 зап/сек).
      </CardDescription>
    </CardHeader>
    {#if missingKeys.length > 0}
      <div class="px-6 pb-2">
        <div class="rounded-xl border border-amber-600/40 bg-amber-500/10 px-4 py-3 text-sm">
          Не настроены ключи: {missingKeys.map(keyLabel).join(", ")}. Заполни их в
          <a href="/preferences" class="font-medium underline">Preferences</a>, иначе очередь нельзя запустить.
        </div>
      </div>
    {/if}
    <CardContent class="flex flex-wrap items-center gap-3">
      <Button onclick={addAll} disabled={isAdding} class="gap-2">
        <Plus data-icon="inline-start" />
        Добавить все
      </Button>

      <Button variant="outline" onclick={() => (resyncDialogOpen = true)} disabled={isResyncing} class="gap-2">
        <RotateCw data-icon="inline-start" />
        Re-Sync
      </Button>

      <Button
        onclick={startProcessing}
        disabled={enabled || isAdding || isStarting || missingKeys.length > 0}
        title={missingKeys.length > 0
          ? `Нужны ключи: ${missingKeys.map(keyLabel).join(", ")} (Preferences)`
          : undefined}
        class="gap-2"
      >
        <Play data-icon="inline-start" />
        Start
      </Button>

      <Button
        variant="outline"
        onclick={stopProcessing}
        disabled={!enabled || isStopping}
        class="gap-2"
      >
        <Square data-icon="inline-start" />
        Stop
      </Button>

      <Button
        variant="outline"
        onclick={removeSynced}
        disabled={isRemovingSynced}
        class="gap-2"
      >
        <CheckCheck data-icon="inline-start" />
        Удалить готовые
      </Button>

      <Button variant="destructive" onclick={() => (removeDialogOpen = true)} class="gap-2">
        <Trash2 data-icon="inline-start" />
        Remove all
      </Button>

      <Badge
        variant={enabled ? "default" : "secondary"}
        class={isProcessing ? "animate-pulse text-emerald-600 dark:text-emerald-400" : ""}
      >
        {statusLabel}
      </Badge>

      <div class="flex flex-wrap gap-1 text-xs text-muted-foreground">
        {#each ["pending", "synced", "confirm", "error", "not_found"] as key}
          <span>{stateLabels[key]}: {counters[key] ?? 0}</span>
        {/each}
      </div>
    </CardContent>
  </Card>

  {#snippet beforeCell(cellItem: QueueItem)}
    {#if cellItem.movie_slug}
      <a
        href={`/movies/${cellItem.movie_slug}`}
        data-sveltekit-preload-data="hover"
        class="truncate text-sm font-medium hover:underline"
      >
        {cellItem.snapshot_title}
      </a>
    {:else}
      <div class="truncate text-sm font-medium">{cellItem.snapshot_title}</div>
    {/if}
    {#if cellItem.snapshot_original_title && cellItem.snapshot_original_title !== cellItem.snapshot_title}
      <div class="truncate text-xs text-muted-foreground">{cellItem.snapshot_original_title}</div>
    {/if}
    {#if cellItem.snapshot_year}
      <div class="text-xs text-muted-foreground">{cellItem.snapshot_year}</div>
    {/if}
  {/snippet}

  <div class="flex flex-col gap-2">
    {#if items.length === 0}
      <div class="rounded-lg border border-dashed px-4 py-10 text-center text-sm text-muted-foreground">
        Очередь пуста. Нажмите «Добавить все», чтобы поставить в очередь несинхронизированные фильмы.
      </div>
    {:else}
      <div class="overflow-x-auto rounded-lg border">
        <Table class="w-full table-fixed">
          <TableHeader>
            <TableRow>
              <TableHead class="w-10">№</TableHead>
              <TableHead class="w-40">Статус</TableHead>
              <TableHead>До</TableHead>
              <TableHead>После</TableHead>
              <TableHead>Результат</TableHead>
              <TableHead class="w-44">Поставлен</TableHead>
              <TableHead class="w-44">Синхронизирован</TableHead>
              <TableHead class="w-36">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {#each items as item, i (item.id)}
              <TableRow>
                <TableCell>
                  <span class="text-xs text-muted-foreground">{(page - 1) * PAGE_SIZE + i + 1}</span>
                </TableCell>
                <TableCell>
                  <Badge variant={stateBadgeVariant(item.state)} class={stateBadgeClass(item.state)}>
                    {stateLabels[item.state] ?? item.state}
                  </Badge>
                </TableCell>
                <TableCell>
                  {#if !item.movie_has_tmdb}
                    <HoverCard.Root openDelay={400}>
                      <HoverCard.Trigger class="block min-w-0 text-left">
                        {@render beforeCell(item)}
                      </HoverCard.Trigger>
                      <HoverCard.Content class="w-96" side="right" align="start">
                        <div class="flex gap-3">
                          {#if item.movie_poster_url}
                            <img
                              src={item.movie_poster_url}
                              alt={item.movie_title || item.snapshot_title}
                              class="h-36 w-24 shrink-0 rounded-md object-cover"
                              loading="lazy"
                            />
                          {/if}
                          <div class="min-w-0 space-y-1">
                            <p class="text-sm font-semibold">{item.movie_title || item.snapshot_title}</p>
                            {#if item.movie_original_title && item.movie_original_title !== (item.movie_title || item.snapshot_title)}
                              <p class="truncate text-xs text-muted-foreground">{item.movie_original_title}</p>
                            {/if}
                            {#if item.movie_year}
                              <Badge variant="outline">{item.movie_year}</Badge>
                            {/if}
                            {#if item.movie_description}
                              <p class="line-clamp-6 text-xs text-muted-foreground">{item.movie_description}</p>
                            {:else}
                              <p class="text-xs text-muted-foreground italic">Без описания</p>
                            {/if}
                          </div>
                        </div>
                      </HoverCard.Content>
                    </HoverCard.Root>
                  {:else}
                    {@render beforeCell(item)}
                  {/if}
                </TableCell>
                <TableCell>
                  {#if item.state === "synced" && item.result_title}
                    <div class="truncate text-sm">{item.result_title}</div>
                    {#if item.result_original_title && item.result_original_title !== item.result_title}
                      <div class="truncate text-xs text-muted-foreground">{item.result_original_title}</div>
                    {/if}
                    {#if item.result_year}
                      <div class="text-xs text-muted-foreground">{item.result_year}</div>
                    {/if}
                  {:else}
                    <span class="text-xs text-muted-foreground">—</span>
                  {/if}
                </TableCell>
                <TableCell>
                  {#if item.state === "synced"}
                    <Badge variant="outline" class="border-emerald-600/40 text-emerald-700 dark:text-emerald-400">
                      OK
                    </Badge>
                  {:else if item.state === "in_progress"}
                    <span class="text-xs text-amber-600 dark:text-amber-400">Обработка…</span>
                  {:else if item.result_message}
                    <span class="line-clamp-2 min-w-0 text-xs text-muted-foreground" title={item.result_message}>
                      {item.result_message}
                    </span>
                  {:else}
                    <span class="text-xs text-muted-foreground">—</span>
                  {/if}
                </TableCell>
                <TableCell>
                  <div class="text-xs">{formatDateTime(item.queued_at)}</div>
                </TableCell>
                <TableCell>
                  {#if item.finished_at}
                    <div class="text-xs">{formatDateTime(item.finished_at)}</div>
                  {:else}
                    <span class="text-xs text-muted-foreground">—</span>
                  {/if}
                </TableCell>
                <TableCell>
                  <div class="flex items-center gap-1">
                    <Tooltip.Provider>
                      <Tooltip.Root>
                        <Tooltip.Trigger>
                          <Button
                            href={`/movies/${item.movie_slug}`}
                            target="_blank"
                            rel="noreferrer"
                            variant="ghost"
                            size="icon"
                            aria-label="Открыть фильм"
                            data-sveltekit-preload-data="hover"
                          >
                            <ExternalLink data-icon="inline-start" />
                          </Button>
                        </Tooltip.Trigger>
                        <Tooltip.Content side="bottom" align="center">Открыть</Tooltip.Content>
                      </Tooltip.Root>
                      <Tooltip.Root>
                        <Tooltip.Trigger>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label="Sync using tmdb-id"
                            disabled={!item.movie_slug || syncingIds[item.id] || item.state === "in_progress"}
                            onclick={() => syncOne(item)}
                          >
                            <RefreshCw
                              data-icon="inline-start"
                              class={syncingIds[item.id] ? "animate-spin" : ""}
                            />
                          </Button>
                        </Tooltip.Trigger>
                        <Tooltip.Content side="bottom" align="center">Sync using tmdb-id</Tooltip.Content>
                      </Tooltip.Root>
                      <Tooltip.Root>
                        <Tooltip.Trigger>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label="Удалить из очереди"
                            disabled={deletingIds[item.id]}
                            onclick={() => deleteItem(item)}
                          >
                            <Trash2 data-icon="inline-start" />
                          </Button>
                        </Tooltip.Trigger>
                        <Tooltip.Content side="bottom" align="center">Удалить</Tooltip.Content>
                      </Tooltip.Root>
                    </Tooltip.Provider>
                  </div>
                </TableCell>
              </TableRow>
            {/each}
          </TableBody>
        </Table>
      </div>
      <div class="flex flex-wrap items-center justify-center gap-2 text-sm text-muted-foreground">
        <span>Показаны {rangeStart}–{rangeEnd} из {total}</span>
        {#if totalPages > 1}
          <form onsubmit={submitJump} class="flex items-center gap-2">
            <label for="tmdb-sync-jump">Перейти на страницу:</label>
            <Input
              id="tmdb-sync-jump"
              bind:value={jumpTo}
              type="number"
              min={1}
              max={totalPages}
              placeholder={`1–${totalPages}`}
              class="h-8 w-24"
            />
            <Button type="submit" variant="outline" size="sm">Перейти</Button>
          </form>
        {/if}
      </div>
      <Pagination.Root count={total} perPage={PAGE_SIZE} bind:page>
        {#snippet children({ pages, currentPage })}
          <Pagination.Content>
            <Pagination.Item>
              <Pagination.Previous />
            </Pagination.Item>
            {#each pages as pg (pg.key)}
              {#if pg.type === "ellipsis"}
                <Pagination.Item>
                  <Pagination.Ellipsis />
                </Pagination.Item>
              {:else}
                <Pagination.Item>
                  <Pagination.Link page={pg} isActive={currentPage === pg.value}>
                    {pg.value}
                  </Pagination.Link>
                </Pagination.Item>
              {/if}
            {/each}
            <Pagination.Item>
              <Pagination.Next />
            </Pagination.Item>
          </Pagination.Content>
        {/snippet}
      </Pagination.Root>
    {/if}
  </div>
</div>

<Dialog.Root bind:open={removeDialogOpen}>
  <Dialog.Content class="sm:max-w-md">
    <Dialog.Header>
      <Dialog.Title>Удалить очередь?</Dialog.Title>
      <Dialog.Description>
        Это удалит все записи очереди TMDB sync и остановит обработку. История
        синхронизации будет потеряна.
      </Dialog.Description>
    </Dialog.Header>
    <Dialog.Footer>
      <Button variant="outline" onclick={() => (removeDialogOpen = false)} disabled={isRemoving}>
        Отмена
      </Button>
      <Button variant="destructive" onclick={removeAll} disabled={isRemoving}>
        {isRemoving ? "Удаляю…" : "Удалить всё"}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={resyncDialogOpen}>
  <Dialog.Content class="sm:max-w-md">
    <Dialog.Header>
      <Dialog.Title>Повторная синхронизация?</Dialog.Title>
      <Dialog.Description>
        Будут удалены все успешно завершённые записи очереди, а все фильмы с
        заполненным TMDB ID добавлены в начало очереди для повторной
        синхронизации (без повторного подбора, данные просто обновятся из TMDB).
      </Dialog.Description>
    </Dialog.Header>
    <Dialog.Footer>
      <Button variant="outline" onclick={() => (resyncDialogOpen = false)} disabled={isResyncing}>
        Отмена
      </Button>
      <Button onclick={resyncAll} disabled={isResyncing}>
        {isResyncing ? "Добавляю…" : "Re-Sync"}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={candidateDialogOpen}>
  <Dialog.Content class="sm:max-w-5xl">
    <Dialog.Header>
      <Dialog.Title>
        {candidateDialogMode === "needs_confirmation" ? "Подтверждение TMDB-совпадения" : "Выбор фильма на TMDB"}
      </Dialog.Title>
      <Dialog.Description>
        {#if activeSyncItem}
          {activeSyncItem.snapshot_title}
          {#if activeSyncItem.snapshot_year}
            ({activeSyncItem.snapshot_year})
          {/if}
          —
        {/if}
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

              {#if candidate.overview}
                <p class="line-clamp-3 text-xs leading-relaxed">
                  {candidate.overview}
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