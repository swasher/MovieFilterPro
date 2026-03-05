<script lang="ts">
  import { goto } from "$app/navigation";
  import { invalidateAll } from "$app/navigation";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Badge } from "$lib/components/ui/badge";
  import { Button } from "$lib/components/ui/button";

  let { data } = $props();
  const movie = $derived(data.movie);

  let isSyncing = $state(false);
  let syncStatus = $state<"idle" | "ok" | "error" | "needs_user_choice">("idle");
  let syncMessage = $state("");

  const runTmdbSync = async (forceRematch: boolean) => {
    isSyncing = true;
    syncMessage = "";

    try {
      const response = await fetch(`/api/vault/movies/${movie.slug}/fetch-tmdb`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force_rematch: forceRematch })
      });

      const payload = (await response.json()) as {
        status?: "ok" | "error" | "needs_user_choice";
        message?: string;
        updated_fields?: string[];
      };

      if (!response.ok) {
        syncStatus = "error";
        syncMessage = payload.message ?? `HTTP ${response.status}`;
        return;
      }

      syncStatus = payload.status ?? "ok";
      const updated = payload.updated_fields?.length ? ` Updated: ${payload.updated_fields.join(", ")}.` : "";
      syncMessage = `${payload.message ?? "TMDB sync done."}${updated}`;

      if (syncStatus === "ok") {
        await invalidateAll();
      }
    } catch (error) {
      syncStatus = "error";
      syncMessage = error instanceof Error ? error.message : "Unknown TMDB sync error";
    } finally {
      isSyncing = false;
    }
  };

  const goBack = async () => {
    if (typeof window === "undefined") return;
    if (window.history.length > 1) {
      window.history.back();
      return;
    }
    await goto("/");
  };
</script>

<div class="mx-auto w-full max-w-4xl p-6">
  <div class="mb-4">
    <Button variant="outline" size="sm" onclick={goBack}>Back</Button>
  </div>

  <Card>
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <span>{movie.title}</span>
        {#if movie.year}
          <Badge variant="secondary">{movie.year}</Badge>
        {/if}
      </CardTitle>
      <CardDescription>{movie.original_title || "No original title"}</CardDescription>
    </CardHeader>

    <CardContent class="space-y-4">
      <div class="flex flex-wrap gap-2">
        <Button onclick={() => runTmdbSync(false)} disabled={isSyncing}>
          {isSyncing ? "Sync..." : "Fetch TMDB data"}
        </Button>
        <Button variant="outline" onclick={() => runTmdbSync(true)} disabled={isSyncing}>
          Force Rematch
        </Button>
      </div>

      {#if syncStatus !== "idle"}
        <div class="rounded-md border px-3 py-2 text-sm">
          <p>
            <strong>{syncStatus}</strong>: {syncMessage}
          </p>
        </div>
      {/if}

      {#if movie.poster_url}
        <img src={movie.poster_url} alt={movie.title} class="max-h-96 rounded-md border object-contain" />
      {/if}

      <div class="grid gap-2 text-sm sm:grid-cols-2">
        <p><strong>Type:</strong> {movie.movie_type}</p>
        <p><strong>Status:</strong> {movie.status}</p>
        <p><strong>IMDb:</strong> {movie.imdb_rating ?? "—"}</p>
        <p><strong>Slug:</strong> {movie.slug}</p>
      </div>

      <div>
        <h2 class="mb-1 text-base font-semibold">Description</h2>
        <p class="text-muted-foreground whitespace-pre-wrap text-sm">
          {movie.description || "No description"}
        </p>
      </div>
    </CardContent>
  </Card>
</div>
