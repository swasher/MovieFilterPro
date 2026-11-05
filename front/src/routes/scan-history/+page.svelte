<script lang="ts">
  import { Badge } from "$lib/components/ui/badge";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Button } from "$lib/components/ui/button";
  import * as Dialog from "$lib/components/ui/dialog";
  import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow
  } from "$lib/components/ui/table";
  import { History, ScrollText } from "@lucide/svelte";
  import type { ApiScanLogEntry, ApiScanRun } from "./+page";

  let { data } = $props();

  let dialogOpen = $state(false);
  let activeRun = $state<ApiScanRun | null>(null);
  let entries = $state<ApiScanLogEntry[]>([]);
  let detailLoading = $state(false);
  let detailError = $state("");
  let logRequestSeq = 0;

  const statusLabel = (value: string) => {
    switch (value) {
      case "success":
        return "Успешно";
      case "error":
        return "Ошибка";
      case "cancelled":
        return "Отменён";
      case "rate_limited":
        return "429 (rate limit)";
      case "cloudflare_blocked":
        return "Cloudflare";
      case "running":
        return "Выполняется";
      default:
        return value;
    }
  };

  const statusVariant = (value: string) => {
    switch (value) {
      case "success":
        return "default";
      case "error":
      case "rate_limited":
      case "cloudflare_blocked":
        return "destructive";
      case "cancelled":
        return "secondary";
      case "running":
        return "outline";
      default:
        return "outline";
    }
  };

  const triggerLabel = (value: string) => (value === "scheduled" ? "Плановый" : "Ручной");

  const formatDate = (value: string | null) => {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat("ru-RU", {
      dateStyle: "medium",
      timeStyle: "medium"
    }).format(date);
  };

  const formatShortDate = (value: string | null) => {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    }).format(date);
  };

  const formatTime = (value: string | null) => {
    if (!value) return "—:—:—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    }).format(date);
  };

  const formatScanToDate = (value: string | null) => {
    if (!value) return "—";
    const parts = value.slice(0, 10).split("-");
    return parts.length === 3 ? `${parts[2]}.${parts[1]}.${parts[0]}` : value;
  };

  const formatDuration = (run: ApiScanRun) => {
    if (!run.started_at || !run.finished_at) return "—";
    const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
    if (Number.isNaN(ms) || ms < 0) return "—";
    const total = Math.floor(ms / 1000);
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    if (hours > 0) return `${hours}ч ${minutes}м`;
    if (minutes > 0) return `${minutes}м ${seconds}с`;
    return `${seconds}с`;
  };

  const openLog = async (run: ApiScanRun) => {
    // Защита от гонки: если быстро открыть другой запуск, устаревший ответ не перезапишет лог.
    const seq = ++logRequestSeq;
    activeRun = run;
    entries = [];
    detailError = "";
    detailLoading = true;
    dialogOpen = true;
    try {
      const response = await fetch(`/api/kinozal/scan/history/${run.id}`);
      const payload = await response.json();
      if (seq !== logRequestSeq) return;
      if (!response.ok) throw new Error(payload.detail ?? `HTTP ${response.status}`);
      entries = payload.entries ?? [];
    } catch (error) {
      if (seq === logRequestSeq) {
        detailError = error instanceof Error ? error.message : String(error);
      }
    } finally {
      if (seq === logRequestSeq) detailLoading = false;
    }
  };
</script>

<div class="flex w-full flex-col gap-4 px-4 py-6 md:px-6">
  <Card>
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <History class="size-5" />
        История сканирований
      </CardTitle>
      <CardDescription>
        Персистентный лог запусков сканирования Kinozal (ручных и по расписанию). Хранятся последние 200 запусков.
      </CardDescription>
    </CardHeader>
    <CardContent class="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
      <span>Запусков: {data.runs.length}</span>
      {#if data.apiError}
        <Badge variant="destructive">{data.apiError}</Badge>
      {/if}
    </CardContent>
  </Card>

  {#if data.runs.length === 0}
    <Card>
      <CardContent class="py-8 text-sm text-muted-foreground">
        История пока пуста.
      </CardContent>
    </Card>
  {:else}
    <div class="rounded-xl border bg-card shadow-sm">
      <Table>
        <TableHeader class="bg-muted/40">
          <TableRow>
            <TableHead class="w-44">Начало</TableHead>
            <TableHead class="w-40">Статус</TableHead>
            <TableHead class="w-28">Длительность</TableHead>
            <TableHead class="w-20 text-right">Новых</TableHead>
            <TableHead class="w-28 text-right">До даты</TableHead>
            <TableHead class="w-20 text-right">Строк</TableHead>
            <TableHead class="w-24 text-right">Лог</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {#each data.runs as run (run.id)}
            <TableRow>
              <TableCell class="whitespace-nowrap">
                <div>{formatShortDate(run.started_at)}</div>
                <div class="text-xs text-muted-foreground">{triggerLabel(run.trigger)}</div>
              </TableCell>
              <TableCell>
                <div class="flex flex-col items-start gap-1">
                  <Badge variant={statusVariant(run.status)}>{statusLabel(run.status)}</Badge>
                  {#if run.error_type}
                    <span
                      class="max-w-48 truncate text-xs text-destructive"
                      title={run.error_type + (run.error_message ? ": " + run.error_message : "")}
                    >
                      {run.error_type}{run.error_message ? `: ${run.error_message}` : ""}
                    </span>
                  {/if}
                </div>
              </TableCell>
              <TableCell class="whitespace-nowrap text-muted-foreground">
                {formatDuration(run)}
              </TableCell>
              <TableCell class="text-right tabular-nums">{run.new_movies_count}</TableCell>
              <TableCell class="whitespace-nowrap text-right text-muted-foreground">
                {formatScanToDate(run.scan_to_date)}
              </TableCell>
              <TableCell class="text-right tabular-nums text-muted-foreground">
                {run.entries_count}
              </TableCell>
              <TableCell class="text-right">
                <Button variant="outline" size="sm" class="gap-1.5" onclick={() => openLog(run)}>
                  <ScrollText class="size-3.5" />
                  Лог
                </Button>
              </TableCell>
            </TableRow>
          {/each}
        </TableBody>
      </Table>
    </div>
  {/if}
</div>

<Dialog.Root bind:open={dialogOpen}>
  <Dialog.Content class="flex h-[85vh] max-h-[85vh] flex-col gap-0 p-0 sm:max-w-4xl">
    <Dialog.Header class="gap-2 border-b px-6 py-4 text-left">
      <Dialog.Title class="flex items-center gap-2">
        <ScrollText class="size-5" />
        Лог запуска #{activeRun?.id ?? ""}
      </Dialog.Title>
      <Dialog.Description>
        Подробный лог сканирования Kinozal{#if activeRun?.started_at} от {formatDate(activeRun.started_at)}{/if}
      </Dialog.Description>
      {#if activeRun}
        <div class="flex flex-wrap items-center gap-2 pt-1 text-xs text-muted-foreground">
          <Badge variant={statusVariant(activeRun.status)}>{statusLabel(activeRun.status)}</Badge>
          <Badge variant="outline">{triggerLabel(activeRun.trigger)}</Badge>
          <span>Новых: {activeRun.new_movies_count}</span>
          <span>Строк: {activeRun.entries_count}</span>
          {#if activeRun.finished_at}
            <span>Завершён: {formatDate(activeRun.finished_at)}</span>
          {/if}
          {#if activeRun.scan_to_date}
            <span>До даты: {formatScanToDate(activeRun.scan_to_date)}</span>
          {/if}
        </div>
        {#if activeRun.error_type}
          <p class="text-xs text-destructive">
            {activeRun.error_type}{activeRun.error_message ? `: ${activeRun.error_message}` : ""}
          </p>
        {/if}
      {/if}
    </Dialog.Header>

    <div class="min-h-0 flex-1 overflow-y-auto bg-slate-950 p-4 font-mono text-xs leading-relaxed">
      {#if detailLoading}
        <div class="text-slate-400">Загрузка...</div>
      {:else if detailError}
        <div class="text-rose-400">{detailError}</div>
      {:else if entries.length === 0}
        <div class="text-slate-500">Записей нет.</div>
      {:else}
        <div class="space-y-1">
          {#each entries as entry (entry.id)}
            <div class={entry.level === "error" ? "text-rose-400" : "text-slate-300"}>
              <span class="text-slate-500">[{formatTime(entry.created_at)}]</span>
              <span class="text-slate-600">[{entry.level}]</span>
              <span class="whitespace-pre-wrap break-words">{entry.message}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>

    <Dialog.Footer class="border-t px-6 py-3 sm:justify-between">
      <span class="text-xs text-muted-foreground">
        {detailLoading ? "Загрузка…" : entries.length + " строк лога"}
      </span>
      <Button variant="outline" size="sm" onclick={() => (dialogOpen = false)}>Закрыть</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
