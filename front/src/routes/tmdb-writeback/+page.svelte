<script lang="ts">
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Badge } from "$lib/components/ui/badge";
  import { Separator } from "$lib/components/ui/separator";
  import { RefreshCw, Trash2, Play, ExternalLink, AlertTriangle, CheckCircle2, Clock3, Info, Send } from "@lucide/svelte";

  type Status = {
    writeback_enabled: boolean;
    lists_writeback_enabled: boolean;
    write_token_present: boolean;
    total_user_movies: number;
    total_with_tmdb: number;
    total_without_tmdb: number;
    skip_list_id: number | null;
    lists_initialized: boolean;
    queue_pending: number;
    queue_error: number;
    queue_total: number;
    huey_pending: number | null;
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

  type RecentItem = {
    movie_id: number;
    movie_title: string;
    movie_slug: string;
    tmdb_id: number | null;
    tmdb_media_type: string | null;
    year: number | null;
    watch_status: number | null;
    watch_status_display: string | null;
    is_favorite: boolean;
    rating: number | null;
    updated_at: string | null;
    writeback_status: string;
    writeback_last_error: string | null;
    writeback_next_retry_at: string | null;
    writeback_reason: string | null;
  };

  let status = $state<Status | null>(null);
  let queue = $state<QueueItem[]>([]);
  let total = $state(0);
  let recent = $state<RecentItem[]>([]);
  let recentTotal = $state(0);
  let isLoading = $state(false);
  let error = $state("");
  let pushingSlug = $state<string | null>(null);

  const loadAll = async () => {
    isLoading = true;
    error = "";
    try {
      const [sRes, qRes, rRes] = await Promise.all([
        fetch("/api/vault/tmdb-writeback/status"),
        fetch("/api/vault/tmdb-writeback/queue"),
        fetch("/api/vault/tmdb-writeback/recent?limit=20")
      ]);
      const sData = await sRes.json();
      const qData = await qRes.json();
      const rData = await rRes.json();
      if (!sRes.ok) throw new Error(sData.message ?? `status ${sRes.status}`);
      if (!qRes.ok) throw new Error(qData.message ?? `queue ${qRes.status}`);
      if (!rRes.ok) throw new Error(rData.message ?? `recent ${rRes.status}`);
      status = sData as Status;
      queue = (qData.items ?? []) as QueueItem[];
      total = qData.total ?? queue.length;
      recent = (rData.items ?? []) as RecentItem[];
      recentTotal = rData.total ?? recent.length;
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

  const pushRecent = async (slug: string) => {
    if (!slug) return;
    pushingSlug = slug;
    try {
      const res = await fetch(`/api/vault/movies/${slug}/tmdb-writeback`, { method: "POST" });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.message ?? `HTTP ${res.status}`);
      const results = Array.isArray(payload) ? payload : [];
      const ok = results.filter((r: any) => r.success).length;
      const fail = results.filter((r: any) => !r.success && r.action !== "skipped").length;
      if (fail) {
        const err = results.find((r: any) => r.error)?.error ?? "частично";
        toast.warning(`Push: ok ${ok}, fail ${fail} — ${err}`);
      } else if (ok) {
        toast.success(`Push ok: ${results.map((r: any) => r.action).join(", ")}`);
      } else {
        const reason = results[0]?.error ?? "пропущено (нет tmdb_id/токена/выключено)";
        toast.warning(`Push пропущен: ${reason}`);
      }
      await loadAll();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      pushingSlug = null;
    }
  };

  const fmt = (iso: string | null) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toLocaleString("ru-RU");
  };

  const wbBadgeVariant = (s: string) => {
    if (s === "error") return "destructive";
    if (s === "pending") return "secondary";
    if (s === "synced") return "default";
    if (s === "no_tmdb_id") return "outline";
    return "outline";
  };

  const wbLabel = (s: string) => {
    if (s === "synced") return "synced";
    if (s === "pending") return "pending";
    if (s === "error") return "error";
    if (s === "disabled") return "disabled";
    if (s === "no_tmdb_id") return "no tmdb_id";
    return s;
  };
</script>

<div class="mx-auto flex w-full max-w-4xl flex-col gap-6 pb-8">
  <!-- Header: Error Log -->
  <Card class="border-amber-500/20 bg-gradient-to-br from-background via-background to-amber-500/5">
    <CardHeader>
      <CardTitle class="flex items-center gap-2 text-2xl">
        <AlertTriangle class="size-6 text-amber-500" />
        TMDB Write-back — Error Log
      </CardTitle>
      <CardDescription class="leading-relaxed">
        Журнал ошибок обратной синхронизации <span class="font-mono">Vault → TMDB</span>. Здесь только фильмы, которые <b>не ушли</b> в TMDB. Пустая очередь — это норма: успешные операции не хранятся и сразу удаляются из журнала.
        HUEY-задачи живут 2&nbsp;сек (окно дедупликации) и не попадают в этот список. Ретрай — каждые 10&nbsp;мин, висит до успеха.
      </CardDescription>
    </CardHeader>
  </Card>

  {#if error}
    <Card class="border-destructive/40"><CardContent class="py-4 text-sm text-destructive">{error}</CardContent></Card>
  {/if}

  <!-- Статус -->
  <Card class="border-border/70">
    <CardHeader class="flex flex-row items-center justify-between gap-2">
      <div>
        <CardTitle class="flex items-center gap-2 text-lg"><Info class="size-4" /> Статус</CardTitle>
        <CardDescription>Синхронизация Vault → TMDB (watchlist / favorite / rating / списки)</CardDescription>
      </div>
      <Button variant="outline" size="sm" onclick={loadAll} disabled={isLoading}><RefreshCw class={`size-4 ${isLoading ? "animate-spin" : ""}`} /> Обновить</Button>
    </CardHeader>
    <CardContent class="space-y-2 text-sm">
      {#if status}
        <div class="grid gap-2 md:grid-cols-2">
          <div class="flex justify-between rounded-xl border px-4 py-2"><span>Write-back</span><span class={status.writeback_enabled ? "text-emerald-600 font-medium" : "text-destructive"}>{status.writeback_enabled ? "Вкл" : "Выкл"}</span></div>
          <div class="flex justify-between rounded-xl border px-4 py-2"><span>Write token</span><span class={status.write_token_present ? "text-emerald-600" : "text-destructive"}>{status.write_token_present ? "Present" : "Missing — /tmdb-auth"}</span></div>
          <div class="flex justify-between rounded-xl border px-4 py-2"><span>Skip-лист «Не интересует»</span><span>{status.skip_list_id ? `#${status.skip_list_id}` : "— (создастся при первом SKIP)"}</span></div>
          <div class="flex justify-between rounded-xl border px-4 py-2"><span>Списки инициализированы</span><span>{status.lists_initialized ? "Да" : "Нет — будет при auth"}</span></div>
        </div>
        <div class="flex justify-between rounded-xl border px-4 py-2"><span>UserMovies</span><span>{status.total_user_movies} total · {status.total_with_tmdb} с tmdb_id · {status.total_without_tmdb} без tmdb_id (не синкаются)</span></div>
        <div class="flex justify-between rounded-xl border px-4 py-2"><span>Очередь ошибок</span><span><span class={status.queue_total ? "text-destructive font-medium" : "text-emerald-600"}>{status.queue_total} всего</span> · {status.queue_pending} pending · {status.queue_error} error {#if status.huey_pending !== null}<span class="text-muted-foreground">· HUEY ephemeral {status.huey_pending}</span>{/if}</span></div>
        <div class="rounded-xl border border-dashed bg-muted/20 px-4 py-2 text-xs text-muted-foreground">
          HUEY pending — задачи в 2-секундном окне дедупликации (`vault/services/tmdb_writeback_dispatch.py:24`). Обычно 0. Если видишь число — это быстрые повторные клики, схлопнутся в один запрос.
        </div>
      {:else}
        <div class="text-muted-foreground text-sm">Загрузка...</div>
      {/if}
    </CardContent>
  </Card>

  <!-- Очередь ошибок -->
  <Card class="border-border/70">
    <CardHeader>
      <CardTitle class="flex items-center gap-2 text-lg"><AlertTriangle class="size-4 text-destructive" /> Очередь ошибок — требует внимания ({total})</CardTitle>
      <CardDescription>Каждый фильм — forever до успеха. 401 → нужен re-auth в /tmdb-auth. 429/сеть → ретрай 10&nbsp;мин. Успех — запись исчезает.</CardDescription>
    </CardHeader>
    <CardContent>
      {#if queue.length === 0}
        <div class="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
          <CheckCircle2 class="mx-auto mb-2 size-6 text-emerald-500" />
          Журнал пуст — всё синхронизировано. Успешные операции не логируются.
        </div>
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

  <!-- Последние синхронизации -->
  <Card class="border-border/70">
    <CardHeader>
      <CardTitle class="flex items-center gap-2 text-lg"><Clock3 class="size-4" /> Последние синхронизации ({recentTotal} всего, показано {recent.length})</CardTitle>
      <CardDescription>Последние 20 изменённых UserMovie. Бейдж — текущее состояние write-back для фильма (synced/error/pending/disabled/no_tmdb_id). Пусто в Error Log ≠ не было синков — смотри здесь.</CardDescription>
    </CardHeader>
    <CardContent>
      {#if recent.length === 0}
        <div class="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">Нет UserMovie — добавь фильм в Vault.</div>
      {:else}
        <div class="space-y-2">
          {#each recent as r (r.movie_id)}
            <div class="flex flex-col gap-2 rounded-xl border px-3 py-2.5 md:flex-row md:items-center md:justify-between">
              <div class="min-w-0 flex-1 space-y-1">
                <div class="flex flex-wrap items-center gap-2">
                  <a href={`/movies/${r.movie_slug}`} class="font-medium hover:underline inline-flex items-center gap-1 truncate">{r.movie_title} <ExternalLink class="size-3 opacity-60 shrink-0" /></a>
                  {#if r.year}<span class="text-xs text-muted-foreground">({r.year})</span>{/if}
                  <Badge variant={wbBadgeVariant(r.writeback_status)} class="capitalize">{wbLabel(r.writeback_status)}</Badge>
                  {#if r.watch_status_display}<span class="text-xs rounded-full border px-2 py-0.5">{r.watch_status_display}</span>{/if}
                  {#if r.is_favorite}<span class="text-xs text-red-500">♥ favorite</span>{/if}
                  {#if r.rating}<span class="text-xs text-amber-600">★ {r.rating}</span>{/if}
                </div>
                <div class="text-xs text-muted-foreground truncate">
                  #{r.movie_id}
                  {#if r.tmdb_id}· TMDB {r.tmdb_id} ({r.tmdb_media_type}){:else}· нет tmdb_id{/if}
                  · обновлён {fmt(r.updated_at)}
                  {#if r.writeback_next_retry_at}· next {fmt(r.writeback_next_retry_at)}{/if}
                </div>
                {#if r.writeback_last_error}
                  <div class="text-xs text-destructive break-all whitespace-pre-wrap">{r.writeback_last_error}</div>
                {:else if r.writeback_reason}
                  <div class="text-xs text-muted-foreground">{r.writeback_reason}</div>
                {/if}
              </div>
              <div class="flex shrink-0 gap-2">
                <Button variant="outline" size="sm" disabled={pushingSlug === r.movie_slug || !r.movie_slug} onclick={() => pushRecent(r.movie_slug)}>
                  {#if pushingSlug === r.movie_slug}<RefreshCw class="size-4 animate-spin" />{:else}<Send class="size-4" />{/if}
                  Push to TMDB
                </Button>
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </CardContent>
  </Card>

  <Card class="border-border/70 bg-muted/20">
    <CardHeader>
      <CardTitle class="text-sm">Как это работает</CardTitle>
    </CardHeader>
    <CardContent class="space-y-2 text-xs leading-relaxed text-muted-foreground">
      <div><b>Успех</b> — запись удаляется из Error Log (`vault/services/tmdb_writeback_service.py:418` `_clear_queue_item`). Смотри бейдж на странице фильма или раздел «Последние синхронизации» выше.</div>
      <div><b>Ошибка</b> — создаётся запись forever-очереди (`_upsert_queue_item`). 429 → backoff 10/30/60/120/300с, 401 → `state=error` без авто-ретрая, нужен re-auth.</div>
      <div><b>HUEY</b> — задачи `tmdb_writeback_user_movie` живут 2&nbsp;с в `SqliteHuey` `movie_filter_pro/huey.py:33` и дедуплицируются по ключу `um:&#123;id&#125;` (`tmdb_writeback_dispatch.py:36`). Поэтому «очередь HUEY» в UI не показывается — она эфемерна.</div>
      <div>Логи: <span class="font-mono">logs/debug.log</span> (`vault.tmdb_writeback`).</div>
      <Separator />
      <div class="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" href="/tmdb-auth">TMDB Auth</Button>
        <Button variant="outline" size="sm" href="/preferences">Preferences</Button>
        <Button variant="outline" size="sm" href="/tmdb-sync">TMDB Sync Queue (pull)</Button>
      </div>
    </CardContent>
  </Card>
</div>
