<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import type { Component } from "svelte";
  import { Button } from "$lib/components/ui/button";
  import { Badge } from "$lib/components/ui/badge";
  import * as Card from "$lib/components/ui/card";
  import {
    Ban,
    Bot,
    CircleCheck,
    CircleX,
    Clapperboard,
    Globe,
    Search,
    Sparkles,
    Trash2,
    Zap
  } from "@lucide/svelte";

  type MatchEvent = {
    id: number;
    time: string;
    event: string;
    data: Record<string, unknown>;
  };

  type EventMeta = {
    label: string;
    icon: Component;
    tone: string;
  };

  const MAX_EVENTS = 200;

  let events = $state<MatchEvent[]>([]);
  let isConnected = $state(false);
  let container = $state<HTMLDivElement | null>(null);
  let socket: WebSocket | null = null;
  let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  let eventSeq = 0;

  const EVENT_META: Record<string, EventMeta> = {
    match_start: { label: "Старт", icon: Clapperboard, tone: "text-slate-500" },
    tmdb_search: { label: "TMDB поиск", icon: Search, tone: "text-sky-500" },
    smart_search_start: { label: "Умный поиск", icon: Sparkles, tone: "text-violet-500" },
    web_search: { label: "Веб-поиск", icon: Globe, tone: "text-indigo-500" },
    ai_web_hints: { label: "AI подсказки", icon: Bot, tone: "text-violet-500" },
    ai_score: { label: "AI сравнение", icon: Bot, tone: "text-violet-500" },
    groq_call: { label: "GROQ", icon: Zap, tone: "text-amber-500" },
    ai_choose: { label: "AI выбор", icon: Bot, tone: "text-violet-500" },
    ai_verify: { label: "AI проверка", icon: Bot, tone: "text-violet-500" },
    literal_match: { label: "Дословный матч", icon: CircleCheck, tone: "text-emerald-500" }
  };

  function eventMeta(event: MatchEvent): EventMeta {
    if (event.event === "match_result") {
      const status = String(event.data.status ?? "");
      if (status === "ok") {
        return { label: "Итог: успех", icon: CircleCheck, tone: "text-emerald-500" };
      }
      if (status === "error") {
        return { label: "Итог: ошибка", icon: CircleX, tone: "text-rose-500" };
      }
      return { label: "Итог: нужен выбор", icon: Ban, tone: "text-amber-500" };
    }
    if (event.event === "groq_call" && event.data.ok === false) {
      return { label: "GROQ", icon: CircleX, tone: "text-rose-500" };
    }
    return EVENT_META[event.event] ?? { label: event.event, icon: Sparkles, tone: "text-muted-foreground" };
  }

  function describe(event: MatchEvent): string {
    const data = event.data;
    switch (event.event) {
      case "match_start":
        return `«${data.title ?? "?"}» / «${data.original_title ?? "?"}» (${data.year ?? "—"}) — movie_id=${data.movie_id ?? "?"}`;
      case "tmdb_search":
        return `query="${data.query}" ${data.media_type}${data.year ? ` year=${data.year}` : ""} → ${data.results_count} кандидатов`;
      case "smart_search_start":
        return `movie_id=${data.movie_id ?? "?"} «${data.title ?? ""}»`;
      case "web_search":
        return `${data.engine ?? "провайдер"} — ${data.ok ? "ок" : "ошибка"}`;
      case "ai_web_hints":
        return `clean_title="${data.clean_title ?? ""}" year=${data.llm_year ?? "—"} (+${data.queries_added ?? 0} запросов)`;
      case "ai_score":
        return `tmdb_id=${data.tmdb_id} same_work=${data.same_work ? "да" : "нет"} confidence=${data.confidence}`;
      case "groq_call":
        return data.ok
          ? `tmdb_id=${data.tmdb_id} confidence=${data.confidence}`
          : `tmdb_id=${data.tmdb_id} — запрос не удался`;
      case "ai_choose":
        return `выбран tmdb_id=${data.selected_tmdb_id ?? "—"} confidence=${data.confidence}`;
      case "ai_verify":
        return `same_work=${data.same_work == null ? "нет ответа" : data.same_work ? "да" : "нет"} confidence=${data.confidence ?? "—"}`;
      case "literal_match":
        return `дословное совпадение описаний — tmdb_id=${data.tmdb_id}`;
      case "match_result":
        return `status=${data.status}${data.tmdb_id ? ` tmdb_id=${data.tmdb_id}` : ""}${data.score != null ? ` score=${data.score}` : ""}${data.message ? ` — ${data.message}` : ""}`;
      default:
        return Object.entries(data)
          .map(([key, value]) => `${key}=${value}`)
          .join(" ");
    }
  }

  function handleMessage(raw: string) {
    try {
      const payload = JSON.parse(raw) as Record<string, unknown> & { type?: string; event?: string };
      if (payload.type !== "match_log" || !payload.event) return;
      const { type: _type, event, ...data } = payload;
      events.push({
        id: ++eventSeq,
        time: new Date().toLocaleTimeString(),
        event,
        data
      });
      if (events.length > MAX_EVENTS) {
        events.splice(0, events.length - MAX_EVENTS);
      }
    } catch (error) {
      console.error("Error parsing websocket message:", error);
    }
  }

  function connect() {
    if (typeof window === "undefined" || socket) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;

    try {
      socket = new WebSocket(`${protocol}//${host}/ws/log/`);

      socket.onopen = () => {
        isConnected = true;
        if (reconnectTimeout) {
          clearTimeout(reconnectTimeout);
          reconnectTimeout = null;
        }
      };

      socket.onclose = () => {
        isConnected = false;
        socket = null;
        reconnectTimeout = setTimeout(() => connect(), 3000);
      };

      socket.onerror = (error) => {
        console.error("WebSocket error:", error);
      };

      socket.onmessage = (message) => handleMessage(message.data as string);
    } catch (error) {
      console.error("Failed to establish WebSocket connection:", error);
    }
  }

  function disconnect() {
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
      reconnectTimeout = null;
    }
    if (socket) {
      socket.onclose = null;
      socket.close();
      socket = null;
    }
    isConnected = false;
  }

  function clearLog() {
    events = [];
  }

  onMount(() => {
    connect();
  });

  onDestroy(() => {
    disconnect();
  });

  $effect(() => {
    if (events.length && container) {
      setTimeout(() => {
        if (container) {
          container.scrollTop = container.scrollHeight;
        }
      }, 50);
    }
  });
</script>

<div class="container mx-auto max-w-5xl space-y-4 p-4">
  <Card.Root>
    <Card.Header class="flex-row items-start justify-between gap-4 space-y-0">
      <div class="space-y-1">
        <Card.Title>Match Log</Card.Title>
        <Card.Description>
          Живой лог матчинга TMDB: bulk-синк (HUEY) и ручной sync работают в одном потоке событий.
        </Card.Description>
      </div>
      <div class="flex shrink-0 items-center gap-2">
        <div class="flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium">
          {#if isConnected}
            <span class="relative flex h-2 w-2">
              <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
              <span class="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
            </span>
            <span class="select-none text-emerald-600 dark:text-emerald-400">websocket подключен</span>
          {:else}
            <span class="relative inline-flex h-2 w-2 rounded-full bg-rose-500"></span>
            <span class="select-none text-rose-600 dark:text-rose-400">websocket отключен</span>
          {/if}
        </div>
        <Button variant="outline" size="sm" class="gap-2" onclick={clearLog}>
          <Trash2 class="size-4" />
          Очистить
        </Button>
      </div>
    </Card.Header>
    <Card.Content>
      <div bind:this={container} class="h-[650px] overflow-y-auto rounded-lg border bg-muted/20">
        {#if events.length === 0}
          <div class="select-none py-20 text-center text-sm italic text-muted-foreground">
            Событий пока нет. Запусти TMDB sync или нажми «▶» у фильма.
          </div>
        {:else}
          <div class="divide-y">
            {#each events as event (event.id)}
              {@const meta = eventMeta(event)}
              {@const Icon = meta.icon}
              <div class="flex items-start gap-3 px-3 py-2">
                <Icon class="mt-0.5 size-4 shrink-0 {meta.tone}" />
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <Badge variant="outline">{meta.label}</Badge>
                    <span class="text-xs text-muted-foreground">{event.time}</span>
                  </div>
                  <div class="mt-1 break-words font-mono text-xs leading-relaxed">
                    {describe(event)}
                  </div>
                </div>
              </div>
            {/each}
          </div>
        {/if}
      </div>
      <p class="mt-2 text-xs text-muted-foreground">
        Лог хранится только в памяти браузера (последние {MAX_EVENTS} событий) и обнуляется при перезагрузке.
      </p>
    </Card.Content>
  </Card.Root>
</div>
