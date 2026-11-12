<script lang="ts">
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import { Badge } from "$lib/components/ui/badge";
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
  import { ExternalLink, RefreshCw } from "@lucide/svelte";
  import {
    parseQbtApiError,
    type QbtApiErrorDetail,
    type QbtTorrent,
    type QbtTorrentsResponse
  } from "$lib/qbittorrent";

  let { data } = $props();

  let items = $state<QbtTorrent[]>([]);
  let total = $state<number>(0);
  let apiError = $state<QbtApiErrorDetail>({ message: "" });
  let unconfigured = $state<boolean>(false);
  let isLoading = $state(false);

  $effect(() => {
    items = data.items ?? [];
    total = data.total ?? 0;
    apiError = data.apiError ?? { message: "" };
    unconfigured = data.unconfigured === true;
  });

  const formatBytes = (value: number): string => {
    if (!Number.isFinite(value) || value <= 0) return "—";
    const units = ["B", "KiB", "MiB", "GiB", "TiB"];
    let size = value;
    let index = 0;
    while (size >= 1024 && index < units.length - 1) {
      size /= 1024;
      index += 1;
    }
    return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
  };

  const formatSpeed = (value: number): string => {
    if (!Number.isFinite(value) || value <= 0) return "—";
    return `${formatBytes(value)}/s`;
  };

  const formatEta = (seconds: number): string => {
    if (!Number.isFinite(seconds) || seconds <= 0 || seconds >= 8640000) return "—";
    const totalSeconds = Math.floor(seconds);
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    if (days > 0) return `${days}д ${hours}ч`;
    if (hours > 0) return `${hours}ч ${minutes}м`;
    return `${minutes}м`;
  };

  const formatProgress = (progress: number): string => {
    const clamped = Math.min(1, Math.max(0, Number.isFinite(progress) ? progress : 0));
    return `${Math.round(clamped * 100)}%`;
  };

  const stateLabel = (state: string): string => {
    const labels: Record<string, string> = {
      downloading: "Скачивание",
      forcedDL: "Скачивание",
      metaDL: "Метаданные",
      stalledDL: "Ожидание",
      queuedDL: "В очереди",
      allocating: "Распределение",
      checkingDL: "Проверка",
      checkingUP: "Проверка",
      checkingResumeData: "Проверка",
      pausedDL: "Пауза",
      pausedUP: "Пауза",
      stoppedDL: "Остановлено",
      stoppedUP: "Остановлено",
      uploading: "Раздача",
      forcedUP: "Раздача",
      stalledUP: "Раздача",
      queuedUP: "В очереди",
      error: "Ошибка",
      missingFiles: "Файлы не найдены",
      moving: "Перемещение"
    };
    return labels[state] ?? state ?? "—";
  };

  const stateVariant = (state: string): "default" | "secondary" | "destructive" | "outline" => {
    if (state === "error" || state === "missingFiles") return "destructive";
    if (["downloading", "forcedDL", "metaDL", "checkingDL", "checkingUP", "checkingResumeData"].includes(state)) {
      return "default";
    }
    if (["uploading", "forcedUP", "stalledUP", "queuedUP"].includes(state)) return "outline";
    return "secondary";
  };

  const refresh = async () => {
    isLoading = true;
    try {
      const response = await fetch("/api/qbittorrent/torrents?limit=500");
      const payload = await response.json();

      if (!response.ok) {
        apiError = parseQbtApiError(payload, `HTTP ${response.status}`);
        unconfigured = [
          "qbt_not_configured",
          "qbt_auth_failed",
          "qbt_invalid_url",
          "qbt_unreachable",
          "qbt_ssl_error",
          "qbt_forbidden",
          "qbt_unauthorized"
        ].includes(apiError.code ?? "");
        items = [];
        total = 0;
        toast.error(apiError.message ?? "Не удалось загрузить раздачи.");
        return;
      }

      const payloadData = payload as QbtTorrentsResponse;
      items = payloadData.items ?? [];
      total = payloadData.total ?? 0;
      apiError = { message: "" };
      unconfigured = false;
    } catch (error) {
      apiError = {
        message: error instanceof Error ? error.message : "Не удалось загрузить список раздач."
      };
      toast.error(apiError.message ?? "Не удалось загрузить список раздач.");
    } finally {
      isLoading = false;
    }
  };
</script>

<div class="mx-auto flex w-full max-w-[1500px] flex-col gap-6 p-4 pb-8">
  <Card class="border-border/70">
    <CardHeader class="gap-4 md:flex-row md:items-start md:justify-between">
      <div class="space-y-2">
        <CardTitle class="text-2xl">qBittorrent</CardTitle>
        <CardDescription>
          Список раздач qBittorrent. Данные обновляются по кнопке «Обновить» или по F5.
        </CardDescription>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <span class="text-sm text-muted-foreground">Всего: {total}</span>
        <Button variant="outline" onclick={refresh} disabled={isLoading}>
          <RefreshCw class={isLoading ? "mr-2 size-4 animate-spin" : "mr-2 size-4"} />
          {isLoading ? "Обновление..." : "Обновить"}
        </Button>
      </div>
    </CardHeader>
  </Card>

  {#if apiError.message}
    <Card class="border-destructive/40">
      <CardContent class="space-y-3 py-4">
        <div class="space-y-1">
          <p class="text-sm font-semibold text-destructive">{apiError.message}</p>
          {#if apiError.hint}
            <p class="text-sm text-muted-foreground">{apiError.hint}</p>
          {/if}
        </div>
        <div class="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onclick={refresh} disabled={isLoading}>
            <RefreshCw class="mr-2 size-4" />
            Повторить
          </Button>
          {#if unconfigured}
            <Button variant="secondary" size="sm" href="/preferences">Открыть Preferences</Button>
          {/if}
        </div>
      </CardContent>
    </Card>
  {:else if items.length === 0}
    <Card class="border-border/70">
      <CardContent class="py-10 text-center text-sm text-muted-foreground">
        В qBittorrent нет раздач.
      </CardContent>
    </Card>
  {:else}
    <Card class="border-border/70">
      <CardContent class="overflow-x-auto p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead class="min-w-[320px]">Раздача</TableHead>
              <TableHead>Состояние</TableHead>
              <TableHead>Прогресс</TableHead>
              <TableHead>Размер</TableHead>
              <TableHead>Скорость</TableHead>
              <TableHead>ETA</TableHead>
              <TableHead class="min-w-[180px]">Vault</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {#each items as item (item.info_hash)}
              <TableRow>
                <TableCell class="max-w-[520px]">
                  <div class="truncate font-medium" title={item.name}>{item.name}</div>
                  <div class="mt-1 font-mono text-xs text-muted-foreground" title={item.info_hash}>
                    {item.info_hash.slice(0, 16)}…
                  </div>
                  {#if item.source_url}
                    <a
                      href={item.source_url}
                      target="_blank"
                      rel="noreferrer"
                      class="mt-1 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                    >
                      <ExternalLink class="size-3" />
                      Раздача
                    </a>
                  {/if}
                  {#if item.category || item.tags.length > 0}
                    <div class="mt-1 flex flex-wrap gap-1">
                      {#if item.category}
                        <Badge variant="secondary" class="text-[10px]">{item.category}</Badge>
                      {/if}
                      {#each item.tags as tag (tag)}
                        <Badge variant="outline" class="text-[10px]">{tag}</Badge>
                      {/each}
                    </div>
                  {/if}
                </TableCell>
                <TableCell>
                  <Badge variant={stateVariant(item.state)}>{stateLabel(item.state)}</Badge>
                </TableCell>
                <TableCell class="tabular-nums">{formatProgress(item.progress)}</TableCell>
                <TableCell class="tabular-nums">{formatBytes(item.size || item.total_size)}</TableCell>
                <TableCell class="tabular-nums">
                  <div>↓ {formatSpeed(item.dlspeed)}</div>
                  <div class="text-xs text-muted-foreground">↑ {formatSpeed(item.upspeed)}</div>
                </TableCell>
                <TableCell class="tabular-nums">{formatEta(item.eta)}</TableCell>
                <TableCell>
                  {#if item.linked_movie}
                    <a class="text-primary underline underline-offset-4" href={`/movies/${item.linked_movie.slug}`}>
                      {item.linked_movie.title}
                    </a>
                  {:else}
                    <span class="text-muted-foreground">—</span>
                  {/if}
                </TableCell>
              </TableRow>
            {/each}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  {/if}
</div>
