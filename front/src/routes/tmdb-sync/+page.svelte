<script lang="ts">
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
  import * as Tooltip from "$lib/components/ui/tooltip";
  import { CheckCheck, ExternalLink, Play, Plus, Square, Trash2 } from "@lucide/svelte";

  let { data } = $props();

  type QueueItem = {
    id: number;
    movie_id: number;
    movie_slug: string;
    movie_title: string;
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

  type QueueState = {
    enabled: boolean;
    delay_seconds: number;
    counters: Record<string, number>;
    total_unsynced: number;
  };

  let enabled = $state(data.state?.enabled ?? false);
  let delaySeconds = $state(data.state?.delay_seconds ?? 60);
  let counters = $state<Record<string, number>>(data.state?.counters ?? {});
  let totalUnsynced = $state(data.state?.total_unsynced ?? 0);
  let items = $state<QueueItem[]>(data.items ?? []);
  let apiError = $state(data.apiError);

  let isAdding = $state(false);
  let isStarting = $state(false);
  let isStopping = $state(false);
  let isRemoving = $state(false);
  let isRemovingSynced = $state(false);
  let removeDialogOpen = $state(false);
  let delayInput = $state(String(delaySeconds));
  let isSavingDelay = $state(false);
  let deletingIds = $state<Record<number, boolean>>({});

  const handleUnauthorized = async (status: number, message?: string): Promise<boolean> => {
    if (status !== 401) return false;
    toast.error(message ?? "Нужно войти в систему.");
    await goto("/login");
    return true;
  };

  const refresh = async () => {
    const [stateResponse, itemsResponse] = await Promise.all([
      fetch("/api/vault/tmdb-sync/state"),
      fetch("/api/vault/tmdb-sync/items?limit=500")
    ]);

    if (stateResponse.ok) {
      const payload = (await stateResponse.json()) as QueueState;
      enabled = payload.enabled;
      delaySeconds = payload.delay_seconds;
      counters = payload.counters;
      totalUnsynced = payload.total_unsynced;
    } else if (stateResponse.status === 401) {
      await handleUnauthorized(401);
      return;
    }

    if (itemsResponse.ok) {
      items = (((await itemsResponse.json()) as { items: QueueItem[] }).items ?? []).map(
        (item) => ({ ...item })
      );
    }
  };

  // Polling: пауза на скрытой вкладке, чаще при активной обработке.
  $effect(() => {
    const intervalMs = enabled ? 2000 : 3000;
    let timer: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      if (timer) return;
      timer = setInterval(refresh, intervalMs);
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

  const startProcessing = async () => {
    isStarting = true;
    try {
      const response = await fetch("/api/vault/tmdb-sync/start", { method: "POST" });
      if (!response.ok) {
        if (await handleUnauthorized(response.status)) return;
        toast.error(`HTTP ${response.status}`);
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
      toast.success(`Запись «${item.snapshot_title}» удалена из очереди.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось удалить запись из очереди");
    } finally {
      deletingIds = { ...deletingIds, [item.id]: false };
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

  const saveDelay = async () => {
    const parsed = parseInt(delayInput, 10);
    if (isNaN(parsed) || parsed < 1 || parsed > 3600) {
      delayInput = String(delaySeconds);
      toast.error("Темп должен быть в диапазоне 1..3600 секунд");
      return;
    }
    isSavingDelay = true;
    try {
      const response = await fetch("/api/vault/tmdb-sync/state", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ delay_seconds: parsed })
      });
      if (!response.ok) {
        if (await handleUnauthorized(response.status)) return;
        toast.error(`HTTP ${response.status}`);
        return;
      }
      delaySeconds = parsed;
      toast.success(`Темп: 1 фильм в ${parsed} сек.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось сохранить темп");
    } finally {
      isSavingDelay = false;
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
        Массовая синхронизация фильмотеки с TMDB: 1 фильм за проход, темп
        задаётся полем ниже. Очередь: {counters.pending ?? 0} записей
        из {totalUnsynced} несинхронизированных.
      </CardDescription>
    </CardHeader>
    <CardContent class="flex flex-wrap items-center gap-3">
      <Button onclick={addAll} disabled={isAdding} class="gap-2">
        <Plus data-icon="inline-start" />
        Добавить все
      </Button>

      <Button
        onclick={startProcessing}
        disabled={enabled || isAdding}
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

      <div class="flex items-center gap-2">
        <span class="text-sm text-muted-foreground">Темп:</span>
        <div class="w-20">
          <Input
            type="number"
            min={1}
            max={3600}
            bind:value={delayInput}
            onblur={saveDelay}
            disabled={isSavingDelay}
          />
        </div>
        <span class="text-sm text-muted-foreground">сек / фильм</span>
      </div>

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

  <div class="flex flex-col gap-2">
    {#if items.length === 0}
      <div class="rounded-lg border border-dashed px-4 py-10 text-center text-sm text-muted-foreground">
        Очередь пуста. Нажмите «Добавить все», чтобы поставить в очередь несинхронизированные фильмы.
      </div>
    {:else}
      <div class="overflow-x-auto rounded-lg border">
        <Table class="w-full">
          <TableHeader>
            <TableRow>
              <TableHead class="w-40">Статус</TableHead>
              <TableHead>До</TableHead>
              <TableHead>После</TableHead>
              <TableHead>Результат</TableHead>
              <TableHead class="w-44">Поставлен</TableHead>
              <TableHead class="w-44">Синхронизирован</TableHead>
              <TableHead class="w-28">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {#each items as item (item.id)}
              <TableRow>
                <TableCell>
                  <Badge variant={stateBadgeVariant(item.state)} class={stateBadgeClass(item.state)}>
                    {stateLabels[item.state] ?? item.state}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div class="text-sm font-medium">{item.snapshot_title}</div>
                  {#if item.snapshot_original_title && item.snapshot_original_title !== item.snapshot_title}
                    <div class="text-xs text-muted-foreground">{item.snapshot_original_title}</div>
                  {/if}
                  {#if item.snapshot_year}
                    <div class="text-xs text-muted-foreground">{item.snapshot_year}</div>
                  {/if}
                </TableCell>
                <TableCell>
                  {#if item.state === "synced" && item.result_title}
                    <div class="text-sm">{item.result_title}</div>
                    {#if item.result_original_title && item.result_original_title !== item.result_title}
                      <div class="text-xs text-muted-foreground">{item.result_original_title}</div>
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
                    <span class="line-clamp-2 max-w-md text-xs text-muted-foreground" title={item.result_message}>
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