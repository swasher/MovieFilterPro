<script lang="ts">
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Input } from "$lib/components/ui/input";
  import { Badge } from "$lib/components/ui/badge";
  import { Separator } from "$lib/components/ui/separator";
  import { ExternalLink, KeyRound, CheckCircle2, LogOut, RefreshCw } from "@lucide/svelte";

  type AuthStatus = {
    api_key_present: boolean;
    api_key_preview: string | null;
    read_token_present: boolean;
    read_token_preview: string | null;
    write_token_present: boolean;
    write_token_preview: string | null;
  };

  let auth = $state<AuthStatus | null>(null);
  let authError = $state("");
  let isLoadingAuth = $state(false);

  // step 1: prefs editing
  let apiKey = $state("");
  let readToken = $state("");
  let isSavingPrefs = $state(false);
  let prefsLoaded = $state(false);

  // step 2-4
  let approveUrl = $state("");
  let requestToken = $state("");
  let isStarting = $state(false);
  let isApproving = $state(false);
  let isLoggingOut = $state(false);
  let startError = $state("");
  let approveError = $state("");

  const loadAuth = async () => {
    isLoadingAuth = true;
    authError = "";
    try {
      const res = await fetch("/api/vault/tmdb-auth/status");
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.message ?? `HTTP ${res.status}`);
      auth = payload as AuthStatus;
    } catch (e) {
      authError = e instanceof Error ? e.message : String(e);
    } finally {
      isLoadingAuth = false;
    }
  };

  const loadPrefs = async () => {
    try {
      const res = await fetch("/api/core/preferences");
      const payload = await res.json();
      if (!res.ok) return;
      apiKey = payload.tmdb_api_key ?? "";
      readToken = payload.tmdb_v4_read_access_token ?? "";
      prefsLoaded = true;
    } catch {}
  };

  $effect(() => {
    void loadAuth();
    void loadPrefs();
  });

  const savePrefs = async () => {
    isSavingPrefs = true;
    try {
      // need to PUT full preferences payload — fetch current then patch two fields
      const curRes = await fetch("/api/core/preferences");
      const cur = await curRes.json();
      if (!curRes.ok) throw new Error(cur.detail ?? "Не удалось загрузить preferences");
      const payload = {
        ...cur,
        tmdb_api_key: apiKey.trim() || null,
        tmdb_v4_read_access_token: readToken.trim() || null
      };
      const res = await fetch("/api/core/preferences", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
      toast.success("TMDB ключи сохранены");
      await loadAuth();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      isSavingPrefs = false;
    }
  };

  const startAuth = async () => {
    isStarting = true;
    startError = "";
    approveUrl = "";
    requestToken = "";
    try {
      const res = await fetch("/api/vault/tmdb-auth/start", { method: "POST" });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.message ?? payload.detail ?? `HTTP ${res.status}`);
      approveUrl = payload.approve_url;
      requestToken = payload.request_token;
      toast.success("Request token создан — перейди по ссылке и нажми Approve");
    } catch (e) {
      startError = e instanceof Error ? e.message : String(e);
      toast.error(startError);
    } finally {
      isStarting = false;
    }
  };

  const finishAuth = async () => {
    isApproving = true;
    approveError = "";
    try {
      const res = await fetch("/api/vault/tmdb-auth/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_token: requestToken || undefined })
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.message ?? payload.detail ?? `HTTP ${res.status}`);
      toast.success("TMDB Write token сохранён");
      approveUrl = "";
      requestToken = "";
      await loadAuth();
    } catch (e) {
      approveError = e instanceof Error ? e.message : String(e);
      toast.error(approveError);
    } finally {
      isApproving = false;
    }
  };

  const logout = async () => {
    isLoggingOut = true;
    try {
      const res = await fetch("/api/vault/tmdb-auth/logout", { method: "POST" });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.message ?? `HTTP ${res.status}`);
      toast.success("Выход из TMDB выполнен");
      await loadAuth();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      isLoggingOut = false;
    }
  };
</script>

<div class="mx-auto flex w-full max-w-3xl flex-col gap-6 pb-8">
  <Card class="border-border/70 bg-gradient-to-br from-background via-background to-muted/30">
    <CardHeader>
      <CardTitle class="text-2xl flex items-center gap-2"><KeyRound class="size-5" /> TMDB Auth</CardTitle>
      <CardDescription>4 шага для получения Write Access Token (V4) — нужен для обратной синхронизации Vault → TMDB.</CardDescription>
    </CardHeader>
  </Card>

  {#if authError}
    <Card class="border-destructive/40"><CardContent class="py-4 text-sm text-destructive">{authError}</CardContent></Card>
  {/if}

  <!-- Status -->
  <Card class="border-border/70">
    <CardHeader>
      <CardTitle class="text-lg">Статус</CardTitle>
    </CardHeader>
    <CardContent class="space-y-2 text-sm">
      <div class="flex justify-between rounded-xl border px-4 py-2"><span>TMDB API key</span><span>{auth?.api_key_present ? `✓ ${auth.api_key_preview}` : "— не задан"}</span></div>
      <div class="flex justify-between rounded-xl border px-4 py-2"><span>Read access token (V4)</span><span>{auth?.read_token_present ? `✓ ${auth.read_token_preview}` : "— не задан"}</span></div>
      <div class="flex justify-between rounded-xl border px-4 py-2"><span>Write access token</span>
        {#if auth?.write_token_present}
          <span class="flex items-center gap-2"><CheckCircle2 class="size-4 text-emerald-500" /> {auth.write_token_preview} <Button variant="outline" size="sm" onclick={logout} disabled={isLoggingOut}>{isLoggingOut ? "Выход..." : "Logout"}</Button></span>
        {:else}
          <span>— не создан</span>
        {/if}
      </div>
    </CardContent>
  </Card>

  <!-- Step 1 -->
  <Card class="border-border/70">
    <CardHeader><CardTitle class="text-lg">Шаг 1 — Ключи TMDB</CardTitle><CardDescription>Возьми TMDB API key и V4 Read Access Token на <a href="https://www.themoviedb.org/settings/api" target="_blank" rel="noreferrer" class="underline">themoviedb.org/settings/api</a> и вставь ниже → Сохранить.</CardDescription></CardHeader>
    <CardContent class="space-y-4">
      <div class="space-y-2"><div class="text-sm font-medium">TMDB API key (V3)</div><Input bind:value={apiKey} placeholder="32-символьный key" /></div>
      <div class="space-y-2"><div class="text-sm font-medium">TMDB V4 Read Access Token</div><Input bind:value={readToken} placeholder="eyJhbGciOi..." /></div>
      <div class="flex gap-3"><Button onclick={savePrefs} disabled={isSavingPrefs}>{isSavingPrefs ? "Сохранение..." : "Сохранить ключи"}</Button><Button variant="outline" href="/preferences">Открыть Preferences</Button></div>
      {#if !prefsLoaded}<div class="text-xs text-muted-foreground">Загрузка текущих ключей...</div>{/if}
    </CardContent>
  </Card>

  <!-- Step 2 -->
  <Card class="border-border/70">
    <CardHeader><CardTitle class="text-lg">Шаг 2 — Start auth</CardTitle><CardDescription>Создаёт request_token на TMDB (нужен read token из шага 1).</CardDescription></CardHeader>
    <CardContent class="space-y-3">
      <Button onclick={startAuth} disabled={isStarting || !auth?.read_token_present}>{isStarting ? "Создание..." : "Start auth"}</Button>
      {#if startError}<div class="text-sm text-destructive">{startError}</div>{/if}
      {#if requestToken}
        <div class="rounded-xl border bg-muted/30 p-3 text-sm break-all">
          <div class="font-medium mb-1">request_token создан:</div>
          <div class="font-mono text-xs break-all">{requestToken}</div>
          <div class="text-xs text-muted-foreground mt-1">Переходи к шагу 3 — там откроешь Approve.</div>
        </div>
      {/if}
    </CardContent>
  </Card>

  <!-- Step 3 -->
  <Card class="border-border/70">
    <CardHeader><CardTitle class="text-lg">Шаг 3 — Approve</CardTitle><CardDescription>Перейди по ссылке и нажми <b>Approve</b> на сайте TMDB.</CardDescription></CardHeader>
    <CardContent>
      {#if approveUrl}
        <div class="rounded-xl border bg-muted/30 p-3 text-sm break-all">
          <a href={approveUrl} target="_blank" rel="noreferrer" class="underline break-all flex items-center gap-1"><ExternalLink class="size-4 shrink-0" />{approveUrl}</a>
        </div>
      {:else}
        <div class="text-sm text-muted-foreground">Сначала выполни шаг 2 — появится ссылка.</div>
      {/if}
    </CardContent>
  </Card>

  <!-- Step 4 -->
  <Card class="border-border/70">
    <CardHeader><CardTitle class="text-lg">Шаг 4 — Finish Auth</CardTitle><CardDescription>Вернись сюда и нажми Finish — обмен request_token на Write Access Token.</CardDescription></CardHeader>
    <CardContent class="space-y-3">
      <Button onclick={finishAuth} disabled={isApproving || !requestToken}>{isApproving ? "Сохранение..." : "Finish Auth"}</Button>
      {#if approveError}<div class="text-sm text-destructive">{approveError}</div>{/if}
      {#if !requestToken}<div class="text-xs text-muted-foreground">Кнопка станет активной после шага 2 (нужен request_token).</div>{/if}
      <Separator />
      <div class="text-xs text-muted-foreground">После успеха Write token появится в статусе выше и включится TMDB Write-back. Повторный Approve не нужен до Logout.</div>
    </CardContent>
  </Card>

</div>
