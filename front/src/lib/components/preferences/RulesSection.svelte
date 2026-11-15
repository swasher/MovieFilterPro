<script lang="ts">
  import { Input } from "$lib/components/ui/input";
  import { Separator } from "$lib/components/ui/separator";
  import { getPreferencesStore } from "./store.svelte.js";

  const store = getPreferencesStore();
</script>

<div class="space-y-5">
  <div class="space-y-4">
    <div class="space-y-1">
      <div class="text-sm font-semibold">Strict rules</div>
      <div class="text-muted-foreground text-xs">
        Страны, жанры, год и рейтинг, при которых раздача отбрасывается.
      </div>
    </div>
    <div class="grid gap-4 md:grid-cols-2">
      <div class="space-y-2">
        <div class="text-sm font-medium">Strict countries</div>
        <Input bind:value={store.form.countries} placeholder="СССР, Россия, Индия" />
      </div>
      <div class="space-y-2">
        <div class="text-sm font-medium">Strict genres</div>
        <Input bind:value={store.form.genres} placeholder="Мюзикл" />
      </div>
      <div class="space-y-2">
        <div class="text-sm font-medium">Strict max year</div>
        <Input bind:value={store.form.max_year} type="number" />
      </div>
      <div class="space-y-2">
        <div class="text-sm font-medium">Strict min rating</div>
        <Input bind:value={store.form.min_rating} type="number" min="0" max="10" step="0.1" />
      </div>
    </div>
  </div>

  <Separator />

  <div class="space-y-4">
    <div class="space-y-1">
      <div class="text-sm font-semibold">Low priority rules</div>
      <div class="text-muted-foreground text-xs">
        Что понижает приоритет раздачи, но не отбрасывает её.
      </div>
    </div>
    <div class="grid gap-4 md:grid-cols-2">
      <div class="space-y-2">
        <div class="text-sm font-medium">Low countries</div>
        <Input bind:value={store.form.low_countries} placeholder="Таиланд, Япония, Южная Корея" />
      </div>
      <div class="space-y-2">
        <div class="text-sm font-medium">Low genres</div>
        <Input bind:value={store.form.low_genres} placeholder="Ужасы" />
      </div>
      <div class="space-y-2">
        <div class="text-sm font-medium">Low max year</div>
        <Input bind:value={store.form.low_max_year} type="number" />
      </div>
      <div class="space-y-2">
        <div class="text-sm font-medium">Low min rating</div>
        <Input bind:value={store.form.low_min_rating} type="number" min="0" max="10" step="0.1" />
      </div>
    </div>
  </div>

  <Separator />

  <div class="space-y-2">
    <div class="text-sm font-medium">Ignore title words</div>
    <Input bind:value={store.form.ignore_title} placeholder="camrip, telesync, trailer" />
  </div>
</div>
