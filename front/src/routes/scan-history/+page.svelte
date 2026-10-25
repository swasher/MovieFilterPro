<script lang="ts">
  import { Badge } from "$lib/components/ui/badge";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Button } from "$lib/components/ui/button";
  import type { ApiScanLogEntry, ApiScanRun } from "./+page";

  let { data } = $props();

  let expandedId = $state<number | null>(null);
  let entries = $state<ApiScanLogEntry[]>([]);
  let detailLoading = $state(false);
  let detailError = $state("");

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

  const toggle = async (run: ApiScanRun) => {
    if (expandedId === run.id) {
      expandedId = null;
      entries = [];
      detailError = "";
      return;
    }

    expandedId = run.id;
    entries = [];
    detailLoading = true;
    detailError = "";
    try {
      const response = await fetch(`/api/kinozal/scan/history/${run.id}`);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `HTTP ${response.status}`);
      entries = payload.entries ?? [];
    } catch (error) {
      detailError = error instanceof Error ? error.message : String(error);
    } finally {
      detailLoading = false;
    }
  };
</script>

<div class="flex w-full flex-col gap-4 px-4 py-6 md:px-6">
  <Card>
    <CardHeader>
      <CardTitle>История сканирований</CardTitle>
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
    <div class="grid gap-3">
      {#each data.runs as run (run.id)}
        <Card class={expandedId === run.id ? "border-primary/40" : ""}>
          <CardHeader class="gap-2">
            <div class="flex flex-wrap items-center gap-2">
              <Badge variant={statusVariant(run.status)}>{statusLabel(run.status)}</Badge>
              <Badge variant="outline">{triggerLabel(run.trigger)}</Badge>
              <span class="text-sm text-muted-foreground">{formatDate(run.started_at)}</span>
            </div>
            <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
              {#if run.finished_at}
                <span><strong>Завершён:</strong> {formatDate(run.finished_at)}</span>
              {/if}
              <span><strong>Новых:</strong> {run.new_movies_count}</span>
              {#if run.scan_to_date}
                <span><strong>До даты:</strong> {run.scan_to_date}</span>
              {/if}
              <span><strong>Строк лога:</strong> {run.entries_count}</span>
            </div>
            {#if run.error_type}
              <CardDescription class="text-destructive">
                {run.error_type}{run.error_message ? `: ${run.error_message}` : ""}
              </CardDescription>
            {/if}
          </CardHeader>
          <CardContent>
            <Button variant="outline" size="sm" onclick={() => toggle(run)}>
              {expandedId === run.id ? "Свернуть лог" : "Показать лог"}
            </Button>

            {#if expandedId === run.id}
              <div class="mt-4 rounded-xl border border-border/70 bg-muted/30 p-3">
                {#if detailLoading}
                  <div class="text-sm text-muted-foreground">Загрузка...</div>
                {:else if detailError}
                  <div class="text-sm text-destructive">{detailError}</div>
                {:else if entries.length === 0}
                  <div class="text-sm text-muted-foreground">Записей нет.</div>
                {:else}
                  <div class="max-h-96 overflow-y-auto space-y-1 font-mono text-xs leading-relaxed">
                    {#each entries as entry (entry.id)}
                      <div class={entry.level === "error" ? "text-rose-400" : "text-slate-300"}>
                        <span class="text-slate-500">[{formatDate(entry.created_at)}]</span> {entry.message}
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>
            {/if}
          </CardContent>
        </Card>
      {/each}
    </div>
  {/if}
</div>
