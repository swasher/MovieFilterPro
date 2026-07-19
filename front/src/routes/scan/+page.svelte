<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { ScanLogger } from "$lib/services/scanLogger.svelte";
  import { Button } from "$lib/components/ui/button";
  import * as ToggleGroup from "$lib/components/ui/toggle-group";
  import { Play, Square, Trash2 } from "@lucide/svelte";

  const logger = new ScanLogger();
  let terminalContainer = $state<HTMLDivElement | null>(null);

  // При изменении типа лога, загружаем его начальное состояние с бэкенда
  $effect(() => {
    const _type = logger.logType; 
    logger.loadInitialLogs();
  });

  // Автоматический скролл вниз при добавлении новых строк в лог
  $effect(() => {
    if (logger.logs.length && terminalContainer) {
      setTimeout(() => {
        if (terminalContainer) {
          terminalContainer.scrollTop = terminalContainer.scrollHeight;
        }
      }, 50);
    }
  });

  onMount(async () => {
    await logger.checkStatus();
    logger.connect();
    await logger.loadInitialLogs();
  });

  onDestroy(() => {
    logger.disconnect();
  });
</script>

<div class="container mx-auto p-4 max-w-5xl space-y-4">
  <!-- Панель Управления (лежит свободно) -->
  <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 shadow-sm">
    <div class="flex flex-wrap items-center gap-3">
      {#if !logger.isScanning}
        <Button onclick={() => logger.startScan()} class="gap-2 shadow-sm">
          <Play class="w-4 h-4 fill-current" />
          Запустить скан
        </Button>
      {:else}
        <Button variant="destructive" onclick={() => logger.cancelScan()} class="gap-2 shadow-sm animate-pulse">
          <Square class="w-4 h-4 fill-current" />
          Отменить скан
        </Button>
      {/if}

      <Button variant="outline" onclick={() => logger.clearLog()} class="gap-2">
        <Trash2 class="w-4 h-4" />
        Очистить лог
      </Button>

      <!-- Индикатор статуса WebSocket -->
      <div class="flex items-center gap-2 text-xs font-medium px-3 py-1.5 rounded-full border bg-background border-slate-200 dark:border-slate-800">
        {#if logger.isConnected}
          <span class="relative flex h-2 w-2">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span class="text-emerald-600 dark:text-emerald-400 select-none">
            websocket подключен
          </span>
        {:else}
          <span class="relative flex h-2 w-2">
            <span class="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
          </span>
          <span class="text-rose-600 dark:text-rose-400 select-none">
            websocket отключен
          </span>
        {/if}
      </div>
    </div>

    <!-- Переключатель типов логов -->
    <div class="flex items-center gap-2">
      <span class="text-sm font-medium text-muted-foreground mr-1">Файл лога:</span>
      <ToggleGroup.Root bind:value={logger.logType} type="single" variant="outline" class="bg-background">
        <ToggleGroup.Item value="scan" class="px-3 py-1 text-sm font-semibold">Scan</ToggleGroup.Item>
        <ToggleGroup.Item value="debug" class="px-3 py-1 text-sm font-semibold">Debug</ToggleGroup.Item>
        <ToggleGroup.Item value="error" class="px-3 py-1 text-sm font-semibold">Error</ToggleGroup.Item>
      </ToggleGroup.Root>
    </div>
  </div>

  <!-- Терминал -->
  <div class="rounded-xl overflow-hidden border border-slate-800 bg-slate-950 shadow-2xl">
    <!-- Шапка терминала в стиле macOS -->
    <div class="flex items-center justify-between px-4 py-3 bg-slate-900 border-b border-slate-800">
      <div class="flex items-center gap-1.5">
        <span class="w-3 h-3 rounded-full bg-[#ff5f56]"></span>
        <span class="w-3 h-3 rounded-full bg-[#ffbd2e]"></span>
        <span class="w-3 h-3 rounded-full bg-[#27c93f]"></span>
      </div>
      <span class="text-xs font-mono text-slate-400 select-none">
        {logger.logType}.log — terminal
      </span>
      <span class="w-12"></span> <!-- Spacer для выравнивания по центру -->
    </div>

    <!-- Содержимое терминала (высота зафиксирована на 650px) -->
    <div 
      bind:this={terminalContainer}
      class="p-4 h-[650px] overflow-y-auto font-mono text-sm leading-relaxed text-slate-300 space-y-1.5 scrollbar-thin scrollbar-thumb-slate-800"
    >
      {#if logger.logs.length === 0}
        <div class="text-slate-500 italic text-center py-20 select-none">
          Лог-файл пуст или сообщений нет.
        </div>
      {:else}
        {#each logger.logs as line}
          {#if line.startsWith('ERROR:')}
            <div class="text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/10 font-medium">
              {@html line}
            </div>
          {:else}
            <div class={line.startsWith('DEBUG:') ? 'text-slate-500' : 'text-emerald-400'}>
              {@html line}
            </div>
          {/if}
        {/each}
      {/if}
    </div>
  </div>
</div>

<style>
  /* Кастомная стилизация скроллбара для терминала */
  .scrollbar-thin::-webkit-scrollbar {
    width: 6px;
  }
  .scrollbar-thin::-webkit-scrollbar-track {
    background: transparent;
  }
  .scrollbar-thin::-webkit-scrollbar-thumb {
    background-color: #1e293b;
    border-radius: 3px;
  }
</style>
