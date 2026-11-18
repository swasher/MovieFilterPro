<script lang="ts">
  import { onDestroy } from "svelte";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { Label } from "$lib/components/ui/label";
  import { Skeleton } from "$lib/components/ui/skeleton";
  import * as Dialog from "$lib/components/ui/dialog";
  import * as Select from "$lib/components/ui/select";
  import BootstrapBadge4kFill from "$lib/components/BootstrapBadge4kFill.svelte";
  import BootstrapBadgeSdFill from "$lib/components/BootstrapBadgeSdFill.svelte";
  import { toast } from "svelte-sonner";
  import {
    canFixDownloadErrorInPreferences,
    type KinozalApiErrorDetail,
    type KinozalDirectQuality,
    type KinozalDirectSearchResponse,
    type KinozalDownloadOption,
    type KinozalTorrentDownloadResponse,
    normalizeKinozalClientError,
    parseKinozalApiError
  } from "$lib/kinozal";
  import { Check, CircleDashed, RefreshCw, Search } from "@lucide/svelte";

  type Props = {
    open: boolean;
  };

  let { open = $bindable() }: Props = $props();

  const YEAR_ANY = "any";
  const CURRENT_YEAR = new Date().getFullYear();
  const SEARCH_YEARS: number[] = Array.from(
    { length: CURRENT_YEAR - 1990 + 1 },
    (_, index) => CURRENT_YEAR - index
  );

  let query = $state("");
  let year = $state<string>(YEAR_ANY);
  let quality = $state<KinozalDirectQuality>("4k");
  let searching = $state(false);
  let searched = $state(false);
  let results = $state<KinozalDownloadOption[]>([]);
  let searchError = $state<KinozalApiErrorDetail | null>(null);
  let downloadError = $state<KinozalApiErrorDetail | null>(null);
  let downloadingId = $state<number | null>(null);
  let downloadedId = $state<number | null>(null);
  let closing = $state(false);
  let closeTimer: ReturnType<typeof setTimeout> | null = null;
  // Если запрос висит дольше обычного — вероятно, идёт эскалация Cloudflare.
  const SLOW_HINT_DELAY_MS = 5000;
  let slowHint = $state(false);
  let slowHintTimer: ReturnType<typeof setTimeout> | null = null;

  const startSlowHint = () => {
    stopSlowHint();
    slowHintTimer = setTimeout(() => {
      slowHintTimer = null;
      slowHint = true;
    }, SLOW_HINT_DELAY_MS);
  };

  const stopSlowHint = () => {
    if (slowHintTimer) {
      clearTimeout(slowHintTimer);
      slowHintTimer = null;
    }
    slowHint = false;
  };

  // Каждое открытие диалога — новый поиск.
  $effect(() => {
    if (!open) return;
    query = "";
    year = YEAR_ANY;
    quality = "4k";
    searched = false;
    results = [];
    searchError = null;
    downloadError = null;
    downloadedId = null;
    closing = false;
    stopSlowHint();
    if (closeTimer) {
      clearTimeout(closeTimer);
      closeTimer = null;
    }
  });

  const formatCreatedDate = (value: string) => value.split(" ")[0] || value;

  const runSearch = async () => {
    const trimmed = query.trim();
    if (!trimmed || searching) return;

    searching = true;
    searched = false;
    searchError = null;
    downloadError = null;
    results = [];
    downloadedId = null;
    startSlowHint();

    try {
      const params = new URLSearchParams({ q: trimmed, quality });
      if (year !== YEAR_ANY) {
        params.set("year", year);
      }
      const response = await fetch(`/api/kinozal/search?${params.toString()}`);
      const payload = (await response.json()) as KinozalDirectSearchResponse | { detail?: unknown };

      if (!response.ok) {
        throw parseKinozalApiError(payload, `HTTP ${response.status}`);
      }

      results = (payload as KinozalDirectSearchResponse).items;
      searched = true;
      if (results.length === 0) {
        toast.info("Ничего не найдено на Kinozal.");
      }
    } catch (error) {
      searchError = normalizeKinozalClientError(error, "Не удалось выполнить поиск.");
      toast.error(searchError.message ?? "Не удалось выполнить поиск.");
    } finally {
      searching = false;
      stopSlowHint();
    }
  };

  const scheduleClose = () => {
    closing = true;
    if (closeTimer) {
      clearTimeout(closeTimer);
    }
    closeTimer = setTimeout(() => {
      closeTimer = null;
      closing = false;
      downloadedId = null;
      open = false;
    }, 700);
  };

  const downloadTorrent = async (option: KinozalDownloadOption) => {
    if (closing) return;
    downloadingId = option.id;
    downloadError = null;
    startSlowHint();

    try {
      const response = await fetch(`/api/kinozal/torrents/${option.id}/direct-download`, {
        method: "POST",
        headers: {
          "content-type": "application/json"
        },
        body: JSON.stringify({
          header: option.header,
          title: option.title ?? null,
          original_title: option.original_title ?? null,
          year: option.year ?? null
        })
      });
      const payload = (await response.json()) as KinozalTorrentDownloadResponse | { detail?: unknown };

      if (!response.ok) {
        throw parseKinozalApiError(payload, `HTTP ${response.status}`);
      }

      downloadedId = option.id;
      toast.success((payload as KinozalTorrentDownloadResponse).message);
      scheduleClose();
    } catch (error) {
      downloadError = normalizeKinozalClientError(error, "Скачать torrent-файл не удалось.");
      toast.error(downloadError.message ?? "Скачать torrent-файл не удалось.");
    } finally {
      downloadingId = null;
      stopSlowHint();
    }
  };

  onDestroy(() => {
    if (closeTimer) {
      clearTimeout(closeTimer);
    }
    if (slowHintTimer) {
      clearTimeout(slowHintTimer);
    }
  });
</script>

<Dialog.Root bind:open>
  <Dialog.Content class="sm:max-w-[1100px]">
    <Dialog.Header>
      <Dialog.Title>Скачать фильм</Dialog.Title>
      <Dialog.Description>
        Поиск произвольной раздачи на Kinozal и скачивание в коллекцию.
        <span class="mt-1 block text-xs text-muted-foreground">
          Поиск идёт в 4K; если 4K не найден, автоматически ищется HD. После скачивания фильм
          попадёт в Vault со статусом «Буду смотреть», а torrent добавится в qBittorrent.
        </span>
      </Dialog.Description>
    </Dialog.Header>

    <div class="flex flex-wrap items-end gap-3">
      <div class="min-w-[260px] flex-1 space-y-1.5">
        <Label for="direct-download-query">Название фильма</Label>
        <Input
          id="direct-download-query"
          bind:value={query}
          placeholder="Heart of the Beast..."
          autofocus
          onkeydown={(event) => {
            if (event.key === "Enter") {
              void runSearch();
            }
          }}
        />
      </div>

      <div class="space-y-1.5">
        <Label for="direct-download-year">Год</Label>
        <Select.Root
          type="single"
          value={year}
          onValueChange={(value) => {
            year = value ?? YEAR_ANY;
          }}
        >
          <Select.Trigger id="direct-download-year" class="h-10 w-28" title="Год выхода">
            {year === YEAR_ANY ? "Любой" : year}
          </Select.Trigger>
          <Select.Content class="max-h-72">
            <Select.Item value={YEAR_ANY}>Любой год</Select.Item>
            {#each SEARCH_YEARS as searchYear (searchYear)}
              <Select.Item value={String(searchYear)}>{searchYear}</Select.Item>
            {/each}
          </Select.Content>
        </Select.Root>
      </div>

      <div class="space-y-1.5">
        <Label for="direct-download-quality">Качество</Label>
        <Select.Root
          type="single"
          value={quality}
          onValueChange={(value) => {
            quality = (value === "hd" ? "hd" : "4k") as KinozalDirectQuality;
          }}
        >
          <Select.Trigger id="direct-download-quality" class="h-10 w-28" title="Качество раздачи">
            {quality === "4k" ? "4K" : "HD"}
          </Select.Trigger>
          <Select.Content>
            <Select.Item value="4k">4K</Select.Item>
            <Select.Item value="hd">HD</Select.Item>
          </Select.Content>
        </Select.Root>
      </div>

      <Button onclick={() => void runSearch()} disabled={searching || !query.trim()}>
        {#if searching}
          <CircleDashed class="size-4 animate-spin" />
        {:else}
          <Search class="size-4" />
        {/if}
        Найти
      </Button>
    </div>

    {#if searching}
      <div class="mt-4 grid gap-3">
        <Skeleton class="h-10 w-full" />
        <Skeleton class="h-10 w-full" />
        <Skeleton class="h-10 w-full" />
      </div>
      {#if slowHint}
        <p class="mt-2 text-sm text-muted-foreground">
          Kinozal выполняет проверку Cloudflare — обход защиты может занять до 2 минут. Не закрывай окно.
        </p>
      {/if}
    {:else if searchError}
      <div class="mt-4 space-y-3 rounded-lg border border-destructive/30 px-4 py-4">
        <div class="space-y-1">
          <p class="text-sm font-semibold text-destructive">
            {searchError.message || "Search error"}
          </p>
          {#if searchError.hint}
            <p class="text-sm text-muted-foreground">
              {searchError.hint}
            </p>
          {/if}
        </div>
        <div class="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onclick={() => void runSearch()} disabled={searching}>
            <RefreshCw class="mr-2 size-4" />
            Retry
          </Button>
          {#if canFixDownloadErrorInPreferences(searchError)}
            <Button variant="secondary" size="sm" href="/preferences">
              Open Preferences
            </Button>
          {/if}
        </div>
      </div>
    {:else if searched && results.length === 0}
      <div class="mt-4 rounded-lg border px-4 py-3 text-sm text-muted-foreground">
        Ничего не найдено на Kinozal. Попробуй изменить название или убрать год.
      </div>
    {:else if results.length}
      {#if downloadError}
        <div class="mt-4 space-y-3 rounded-lg border border-destructive/30 px-4 py-4">
          <div class="space-y-1">
            <p class="text-sm font-semibold text-destructive">
              {downloadError.message || "Download error"}
            </p>
            {#if downloadError.hint}
              <p class="text-sm text-muted-foreground">
                {downloadError.hint}
              </p>
            {/if}
          </div>
          {#if canFixDownloadErrorInPreferences(downloadError)}
            <Button variant="secondary" size="sm" href="/preferences">
              Open Preferences
            </Button>
          {/if}
        </div>
      {/if}

      <div class="mt-4 max-h-[60vh] overflow-auto">
        <table class="w-full min-w-[860px] table-fixed border-collapse text-sm">
          <colgroup>
            <col class="w-[520px]" />
            <col class="w-[82px]" />
            <col class="w-[64px]" />
            <col class="w-[64px]" />
            <col class="w-[92px]" />
            <col class="w-[110px]" />
          </colgroup>
          <thead class="bg-muted/50">
            <tr class="text-left">
              <th class="px-2.5 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Title</th>
              <th class="px-2.5 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Size</th>
              <th class="px-2.5 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Seed</th>
              <th class="px-2.5 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Peer</th>
              <th class="px-2.5 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Created</th>
              <th class="px-2.5 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Download</th>
            </tr>
          </thead>
          <tbody>
            {#each results as option (option.id)}
              <tr class="border-t align-top">
                <td class="px-2.5 py-2.5">
                  <div class="space-y-1">
                    <div class="text-sm leading-5 font-medium">
                      {#if option.is_4k}
                        <BootstrapBadge4kFill class="mr-1 inline-block size-3.5 align-[-0.15em] text-foreground/80" />
                      {/if}
                      {#if option.is_sdr}
                        <BootstrapBadgeSdFill class="mr-1 inline-block size-3.5 align-[-0.15em] text-foreground/80" />
                      {/if}
                      <a
                        href={option.link}
                        target="_blank"
                        rel="noreferrer"
                        class="inline text-sm transition-colors hover:text-primary"
                      >
                        {option.header}
                      </a>
                    </div>
                  </div>
                </td>
                <td class="px-2.5 py-2.5 text-xs">{option.size}</td>
                <td class="px-2.5 py-2.5 text-xs">{option.seed}</td>
                <td class="px-2.5 py-2.5 text-xs">{option.peer}</td>
                <td class="px-2.5 py-2.5 text-xs">{formatCreatedDate(option.created)}</td>
                <td class="px-2.5 py-2.5">
                  <div class="flex">
                    <Button
                      variant="default"
                      size="sm"
                      class="h-7 px-2.5 text-xs"
                      onclick={() => void downloadTorrent(option)}
                      disabled={downloadingId === option.id || closing}
                    >
                      {#if downloadingId === option.id}
                        <CircleDashed class="size-3.5 animate-spin" />
                      {:else if downloadedId === option.id}
                        <Check class="size-3.5" />
                        Скачано
                      {:else}
                        Download
                      {/if}
                    </Button>
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      {#if slowHint}
        <p class="mt-3 text-sm text-muted-foreground">
          Kinozal выполняет проверку Cloudflare — обход защиты может занять до 2 минут. Не закрывай окно.
        </p>
      {/if}
    {:else}
      <div class="mt-4 rounded-lg border px-4 py-3 text-sm text-muted-foreground">
        Введи название фильма и нажми «Найти».
      </div>
    {/if}
  </Dialog.Content>
</Dialog.Root>
