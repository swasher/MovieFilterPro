<script lang="ts">
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Badge } from "$lib/components/ui/badge";
  import { RefreshCw, Trash2, Play, ExternalLink } from "@lucide/svelte";

  type Status = {
    writeback_enabled: boolean;
    lists_writeback_enabled: boolean;
    write_token_present: boolean;
    total_user_movies: number;
    total_with_tmdb: number;
    total_without_tmdb: number;
  };

  type QueueItem = {
    id: number;
    movie_id: number;
    movie_title: string;
    movie_slug: string;
    state: string;
    last_error: string;
    attempts: number;
    next_retry_at: string | null;
    created_at: string;
  };

  let status = $state<Status | null>(null);
  let queue = $state<QueueItem[]>([]);
  let total = $state(0);
  let isLoading = $state(false);
  let error = $state("");

  const loadAll = async () => {
    isLoading = true;
    error = "";
    try {
      const [sRes, qRes] = await Promise.all([
        fetch("/api/vault/tmdb-writeback/status"),
        fetch("/api/vault/tmdb-writeback/queue")
      ]);
      const sData = await sRes.json();
      const qData = await qRes.json();
      if (!sRes.ok) throw new Error(sData.message ?? `status ${sRes.status}`);
      if (!qRes.ok) throw new Error(qData.message ?? `queue ${qRes.status}`);
      status = sData as Status;
      queue = (qData.items ?? []) as QueueItem[];
      total = qData.total ?? queue.length;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      toast.error(error);
    } finally {
      isLoading = false;
    }
  };

  $effect(() => {
    void loadAll();
  });

  const retry = async (id: number) => {
    try {
      const res = await fetch(`/api/vault/tmdb-writeback/queue/${id}/retry`, { method: "POST" });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.message ?? `HTTP ${res.status}`);
      toast.success("Retry отправлен");
      await loadAll();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  };

  const remove = async (id: number) => {
    try {
      const res = await fetch(`/api/vault/tmdb-writeback/queue/${id}`, { method: "DELETE" });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.message ?? `HTTP ${res.status}`);
      toast.success("Удалено из очереди");
      await loadAll();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  };

  const fmt = (iso: string | null) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toLocaleString("ru-RU");
  };
</script>

<div class="mx-auto flex w-full max-w-4xl flex-col gap-6 pb-8">
  <Card class="border-border/70 bg-gradient-to-br from-background via-background to-muted/30">
    <CardHeader>
      <CardTitle class="text-2xl">TMDB Write-back — очередь</CardTitle>
      <CardDescription>Forever-очередь: фильмы, не ушедшие в TMDB. Ретрай каждые 10 минут, висит до успеха. Ручной разбор здесь.</CardDescription>
    </CardHeader>
  </Card>

  {#if error}
    <Card class="border-destructive/40"><CardContent class="py-4 text-sm text-destructive">{error}</CardContent></Card>
  {/if}

  <Card class="border-border/70">
    <CardHeader class="flex flex-row items-center justify-between">
      <div>
        <CardTitle class="text-lg">Статус</CardTitle>
        <CardDescription>Синхронизация Vault → TMDB</CardDescription>
      </div>
      <Button variant="outline" size="sm" onclick={loadAll} disabled={isLoading}><RefreshCw class={`size-4 ${isLoading ? "animate-spin" : ""}`} /> Обновить</Button>
    </CardHeader>
    <CardContent class="space-y-2 text-sm">
      {#if status}
        <div class="flex justify-between rounded-xl border px-4 py-2"><span>Write-back</span><span>{status.writeback_enabled ? "Вкл" : "Выкл"}</span></div>
        <div class="flex justify-between rounded-xl border px-4 py-2"><span>Write token</span><span>{status.write_token_present ? "Present" : "Missing — /tmdb-auth"}</span></div>
        <div class="flex justify-between rounded-xl border px-4 py-2"><span>UserMovies</span><span>{status.total_user_movies} total, {status.total_with_tmdb} с tmdb_id, {status.total_without_tmdb} без</span></div>
        <div class="flex justify-between rounded-xl border px-4 py-2"><span>Очередь</span><span>{total} в очереди (pending/error)</span></div>
      {:else}
        <div class="text-muted-foreground text-sm">Загрузка...</div>
      {/if}
    </CardContent>
  </Card>

  <Card class="border-border/70">
    <CardHeader>
      <CardTitle class="text-lg">Очередь ({total})</CardTitle>
      <CardDescription>Каждый фильм — forever до успеха. Ошибка 401 → нужен re-auth, 429/сеть → ретрай 10м.</CardDescription>
    </CardHeader>
    <CardContent>
      {#if queue.length === 0}
        <div class="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">Очередь пуста — всё синхронизировано.</div>
      {:else}
        <div class="space-y-3">
          {#each queue as item (item.id)}
            <div class="flex flex-col gap-2 rounded-xl border p-3 md:flex-row md:items-center md:justify-between">
              <div class="min-w-0 flex-1 space-y-1">
                <div class="flex items-center gap-2">
                  <a href={`/movies/${item.movie_slug}`} class="font-medium hover:underline flex items-center gap-1">{item.movie_title} <ExternalLink class="size-3 opacity-60" /></a>
                  <Badge variant={item.state === "error" ? "destructive" : "secondary"}>{item.state}</Badge>
                  <span class="text-xs text-muted-foreground">попыток {item.attempts}</span>
                </div>
                <div class="text-xs text-muted-foreground truncate">#{item.movie_id} • {fmt(item.created_at)} • next: {fmt(item.next_retry_at)}</div>
                {#if item.last_error}
                  <div class="text-xs text-destructive break-all whitespace-pre-wrap">{item.last_error}</div>
                {/if}
              </div>
              <div class="flex gap-2 shrink-0">
                <Button variant="outline" size="sm" onclick={() => retry(item.id)}><Play class="size-4" /> Retry</Button>
                <Button variant="outline" size="sm" onclick={() => remove(item.id)}><Trash2 class="size-4" /> Удалить</Button>
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </CardContent>
  </Card>
</div>
