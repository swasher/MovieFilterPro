<script lang="ts">
  import { Badge } from "$lib/components/ui/badge";
  import { Separator } from "$lib/components/ui/separator";
  import { resolveSelectedEndpoint, type AiEndpoint } from "$lib/aiEndpoints";
  import { getPreferencesStore } from "./store.svelte.js";

  type Props = {
    endpoints?: AiEndpoint[];
  };

  let { endpoints = [] }: Props = $props();

  const store = getPreferencesStore();

  type StatusTone = "ok" | "warn" | "off";

  type StatusRow = {
    label: string;
    value: string;
    tone: StatusTone;
  };

  const configured = (ok: boolean, missing = "Missing"): { value: string; tone: StatusTone } =>
    ok ? { value: "Configured", tone: "ok" } : { value: missing, tone: "warn" };

  const activeAiEndpoint = $derived(resolveSelectedEndpoint(endpoints));

  const statusRows = $derived.by<StatusRow[]>(() => {
    const form = store.form;
    const ai = !form.ai_enabled
      ? { value: "Disabled", tone: "off" as StatusTone }
      : !activeAiEndpoint
        ? { value: "No endpoint", tone: "warn" as StatusTone }
        : activeAiEndpoint.base_url.trim() && activeAiEndpoint.model.trim()
          ? { value: activeAiEndpoint.name, tone: "ok" as StatusTone }
          : { value: "Incomplete", tone: "warn" as StatusTone };

    return [
      {
        label: "Kinozal auth",
        ...configured(Boolean(form.cookie_uid.trim() && form.cookie_pass.trim()))
      },
      {
        label: "Зеркала kinozal",
        value: `${form.kinozal_mirrors.length} шт.${form.kinozal_domain ? ` / активно: ${form.kinozal_domain}` : ""}`,
        tone: form.kinozal_mirrors.length ? "ok" : "warn"
      },
      { label: "qBittorrent", ...configured(Boolean(form.qbt_url.trim())) },
      { label: "Torrent backup folder", ...configured(Boolean(form.torrents_backup_folder.trim())) },
      { label: "TMDB read token", ...configured(Boolean(form.tmdb_v4_read_access_token.trim())) },
      { label: "OMDB API key", ...configured(Boolean(form.omdb_api_key.trim())) },
      {
        label: "Веб-поиск",
        value: form.searxng_url.trim() ? "SearXNG" : form.tavily_api_key.trim() ? "Tavily" : "Missing",
        tone: form.searxng_url.trim() || form.tavily_api_key.trim() ? "ok" : "warn"
      },
      { label: "Plex token", ...configured(Boolean(form.plex_token.trim())) },
      { label: "AI", ...ai }
    ];
  });

  const toneClass = (tone: StatusTone) =>
    tone === "ok"
      ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-400"
      : tone === "warn"
        ? "border-amber-500/40 text-amber-600 dark:text-amber-400"
        : "text-muted-foreground";

  const toneLabel = (tone: StatusTone) => (tone === "ok" ? "настроено" : tone === "warn" ? "проверь" : "выкл");
</script>

<div class="space-y-4">
  <div class="space-y-1">
    <div class="text-sm font-semibold">Состояние настроек</div>
    <div class="text-muted-foreground text-xs">
      Считается по текущим значениям полей — сохранение не требуется.
    </div>
  </div>

  <div class="grid gap-2 sm:grid-cols-2">
    {#each statusRows as row (row.label)}
      <div class="border-border/70 flex items-center justify-between gap-3 rounded-xl border px-4 py-2.5 text-sm">
        <span class="text-muted-foreground min-w-0 truncate">{row.label}</span>
        <Badge variant="outline" class={toneClass(row.tone)}>{row.value}</Badge>
      </div>
    {/each}
  </div>

  <Separator />

  <p class="text-muted-foreground text-xs">
    «{toneLabel("ok")}» — значение задано, «{toneLabel("warn")}» — чего-то не хватает, «{toneLabel("off")}» — фича
    выключена.
  </p>
</div>
