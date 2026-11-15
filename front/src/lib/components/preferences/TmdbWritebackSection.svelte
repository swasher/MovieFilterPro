<script lang="ts">
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import { Label } from "$lib/components/ui/label";
  import { Switch } from "$lib/components/ui/switch";

  // --- TMDB write-back status ---
  let wbEnabled = $state(true);
  let wbListsEnabled = $state(true);
  let wbTokenPresent = $state(false);
  let wbTotal = $state(0);
  let wbWithTmdb = $state(0);
  let wbLoading = $state(false);
  let wbError = $state("");

  const loadWritebackStatus = async () => {
    wbLoading = true;
    wbError = "";
    try {
      const res = await fetch("/api/vault/tmdb-writeback/status");
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.message ?? `HTTP ${res.status}`);
      wbEnabled = payload.writeback_enabled;
      wbListsEnabled = payload.lists_writeback_enabled;
      wbTokenPresent = payload.write_token_present;
      wbTotal = payload.total_user_movies;
      wbWithTmdb = payload.total_with_tmdb;
    } catch (e) {
      wbError = e instanceof Error ? e.message : String(e);
    } finally {
      wbLoading = false;
    }
  };

  const patchWriteback = async (patch: { writeback_enabled?: boolean }) => {
    // optimistic
    if (patch.writeback_enabled !== undefined) wbEnabled = patch.writeback_enabled;
    try {
      const res = await fetch("/api/vault/tmdb-writeback/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch)
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.message ?? `HTTP ${res.status}`);
      wbEnabled = payload.writeback_enabled;
      wbListsEnabled = payload.lists_writeback_enabled;
      toast.success(wbEnabled ? "TMDB write-back включён." : "TMDB write-back выключен.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
      // revert on error
      await loadWritebackStatus();
    }
  };

  $effect(() => {
    void loadWritebackStatus();
  });
</script>

<div class="space-y-4 text-sm">
  {#if wbError}
    <div class="border-destructive/40 bg-destructive/10 text-destructive rounded-xl border px-4 py-3">
      {wbError}
    </div>
  {/if}

  <div class="border-border/70 flex items-center justify-between rounded-xl border px-4 py-3">
    <div class="space-y-1">
      <Label for="wb-enabled" class="text-sm font-medium">TMDB Write-back</Label>
      <div class="text-muted-foreground text-xs">
        Вкл — статусы, оценки и списки уходят в TMDB (создаются на лету). Выкл — всё локально.
      </div>
    </div>
    <Switch
      id="wb-enabled"
      bind:checked={wbEnabled}
      onCheckedChange={(v) => {
        patchWriteback({ writeback_enabled: v });
        return v;
      }}
    />
  </div>

  <div class="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs">
    <span>С TMDB: {wbWithTmdb} из {wbTotal}</span>
    <span>Списки: {wbListsEnabled ? "вкл" : "выкл"}</span>
    <span>Write token: {wbTokenPresent ? "есть" : "нет"}</span>
    {#if wbLoading}
      <span>обновление…</span>
    {/if}
  </div>

  <div class="flex flex-wrap gap-3 pt-1">
    <Button variant="outline" href="/tmdb-auth">TMDB Auth</Button>
    <Button variant="outline" href="/tmdb-writeback">TMDB Write-back Error Log →</Button>
  </div>
</div>
