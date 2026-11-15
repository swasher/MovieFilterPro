<script lang="ts">
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { Label } from "$lib/components/ui/label";
  import { Separator } from "$lib/components/ui/separator";
  import { Switch } from "$lib/components/ui/switch";
  import { getPreferencesStore } from "./store.svelte.js";

  const store = getPreferencesStore();

  let qbtTestLoading = $state(false);
  let qbtTestMessage = $state("");
  let qbtTestError = $state("");

  const savedBackupFolderPath = $derived(store.preferences?.resolved_torrents_backup_folder ?? "");
  const backupFolderExists = $derived(store.preferences?.backup_folder_exists ?? false);
  const backupFolderNeedsRefresh = $derived(
    Boolean(
      store.preferences &&
        store.form.torrents_backup_folder.trim() !== (store.preferences.torrents_backup_folder ?? "")
    )
  );

  const parseQbtTestError = (payload: unknown, fallback: string) => {
    if (!payload || typeof payload !== "object" || !("detail" in payload)) return fallback;
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail.trim();
    if (detail && typeof detail === "object") {
      const record = detail as { message?: unknown; hint?: unknown };
      const message = typeof record.message === "string" ? record.message.trim() : "";
      const hint = typeof record.hint === "string" ? record.hint.trim() : "";
      if (message && hint) return `${message} ${hint}`;
      if (message) return message;
      if (hint) return hint;
    }
    return fallback;
  };

  const asOptionalText = (value: string) => {
    const normalized = value.trim();
    return normalized ? normalized : null;
  };
  const asOptionalSecret = (value: string) => (value ? value : null);

  const testQbtConnection = async () => {
    qbtTestLoading = true;
    qbtTestMessage = "";
    qbtTestError = "";

    try {
      const response = await fetch("/api/qbittorrent/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: asOptionalText(store.form.qbt_url),
          api_key: asOptionalSecret(store.form.qbt_api_key),
          skip_cert_verify: store.form.qbt_skip_cert_verify
        })
      });
      const payload = await response.json();

      if (!response.ok) {
        throw new Error(parseQbtTestError(payload, `HTTP ${response.status}`));
      }

      const version = payload.version ? `qBittorrent ${payload.version}` : "qBittorrent";
      const apiVersion = payload.web_api_version ? `, Web API ${payload.web_api_version}` : "";
      const count = payload.torrent_count ?? 0;
      qbtTestMessage = `Подключение успешно: ${version}${apiVersion}, раздач: ${count}.`;
      toast.success(qbtTestMessage);
    } catch (error) {
      qbtTestError =
        error instanceof Error ? error.message : "Не удалось подключиться к qBittorrent.";
      toast.error(qbtTestError);
    } finally {
      qbtTestLoading = false;
    }
  };
</script>

<div class="space-y-5">
  <div class="grid gap-4 md:grid-cols-2">
    <div class="space-y-2">
      <div class="text-sm font-medium">Web API URL</div>
      <Input bind:value={store.form.qbt_url} placeholder="http://qbittorrent:8080" />
    </div>
    <div class="space-y-2">
      <div class="text-sm font-medium">API-ключ</div>
      <Input
        bind:value={store.form.qbt_api_key}
        type="password"
        placeholder="qbt_..."
        autocomplete="off"
      />
      <div class="text-muted-foreground text-xs">
        qBittorrent 5.2+: Options → Web UI → API keys.
      </div>
    </div>
    <div class="space-y-2 md:col-span-2">
      <div class="text-sm font-medium">Папка backup .torrent</div>
      <Input bind:value={store.form.torrents_backup_folder} placeholder="/app/backup_torrents" />
    </div>
  </div>

  <div class="border-border/70 flex items-center justify-between rounded-xl border px-4 py-3">
    <div class="space-y-1">
      <Label for="qbt-skip-cert-verify" class="text-sm font-medium">
        Не проверять TLS-сертификат
      </Label>
      <div class="text-muted-foreground text-xs">
        Включи, если WebUI работает по HTTPS с самоподписанным сертификатом.
      </div>
    </div>
    <Switch
      id="qbt-skip-cert-verify"
      bind:checked={store.form.qbt_skip_cert_verify}
      onCheckedChange={(v) => {
        store.form.qbt_skip_cert_verify = v;
        store.markDirty();
        return v;
      }}
    />
  </div>

  <div class="flex flex-wrap items-center gap-3">
    <Button variant="outline" onclick={testQbtConnection} disabled={qbtTestLoading}>
      {qbtTestLoading ? "Проверка..." : "Проверить подключение"}
    </Button>
    {#if qbtTestMessage}
      <span class="text-sm text-emerald-600 dark:text-emerald-400">{qbtTestMessage}</span>
    {/if}
    {#if qbtTestError}
      <span class="text-destructive text-sm">{qbtTestError}</span>
    {/if}
  </div>

  <Separator />

  <div class="space-y-4">
    <div class="space-y-1">
      <div class="text-sm font-semibold">Backup folder</div>
      <div class="text-muted-foreground text-xs">
        Как backend разворачивает путь к папке с .torrent-файлами.
      </div>
    </div>

    <div class="border-border/70 bg-muted/40 rounded-2xl border p-4 text-sm">
      <div class="text-muted-foreground">{store.preferences?.backup_folder_hint}</div>
      <div class="mt-3 grid gap-2 md:grid-cols-2">
        <div>
          <div class="text-muted-foreground text-xs tracking-[0.18em] uppercase">Resolved path</div>
          <div class="mt-1 font-mono text-xs break-all">
            {savedBackupFolderPath || "Путь появится после сохранения."}
          </div>
        </div>
        <div>
          <div class="text-muted-foreground text-xs tracking-[0.18em] uppercase">
            Exists on backend
          </div>
          <div class="mt-1">{backupFolderExists ? "Yes" : "No"}</div>
        </div>
      </div>

      {#if backupFolderNeedsRefresh}
        <div class="mt-3 text-amber-600 dark:text-amber-400">
          Поле backup folder изменено. Сохрани настройки, чтобы backend пересчитал resolved path.
        </div>
      {/if}
    </div>

    <p class="text-muted-foreground text-sm">
      В Docker URL обычно выглядит как <span class="font-mono">http://qbittorrent:8080</span>, а папка —
      <span class="font-mono">/app/backup_torrents</span>. Не используй localhost: backend находится в
      отдельном контейнере.
    </p>
  </div>
</div>
