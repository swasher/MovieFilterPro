<script lang="ts">
  import MinusIcon from "@lucide/svelte/icons/minus";
  import PlusIcon from "@lucide/svelte/icons/plus";
  import { toast } from "svelte-sonner";
  import KinozalMirrorDialog from "$lib/components/KinozalMirrorDialog.svelte";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { Label } from "$lib/components/ui/label";
  import * as Select from "$lib/components/ui/select";
  import { Separator } from "$lib/components/ui/separator";
  import { Switch } from "$lib/components/ui/switch";
  import { MAX_KINOZAL_MIRRORS } from "$lib/preferences";
  import { getPreferencesStore } from "./store.svelte.js";
  import { MIN_SCAN_INTERVAL_MINUTES } from "./types.js";

  const store = getPreferencesStore();

  let addMirrorOpen = $state(false);

  // Автосканирование принудительно выключено из settings (dev-компьютер).
  const scanScheduleLocked = $derived(store.preferences?.scan_schedule_locked ?? false);
  const checkpointUrl = $derived.by(() => {
    const checkpointId = store.preferences?.last_scan_kinozal_id;
    const domain = store.preferences?.kinozal_domain;
    return checkpointId != null && domain
      ? `https://${domain}/details.php?id=${checkpointId}`
      : null;
  });

  const lastScheduledRunLabel = $derived(
    store.preferences?.last_scheduled_run_at
      ? new Date(store.preferences.last_scheduled_run_at).toLocaleString()
      : "—"
  );
  const lastScheduledStatusLabel = $derived(
    store.preferences?.last_scheduled_status === "success"
      ? "Успешно"
      : store.preferences?.last_scheduled_status === "error"
        ? "Ошибка"
        : store.preferences?.last_scheduled_status === "cancelled"
          ? "Отменён"
          : (store.preferences?.last_scheduled_status ?? "—")
  );

  const handleAddMirror = (domain: string) => {
    if (store.form.kinozal_mirrors.includes(domain)) return;
    store.form.kinozal_mirrors = [...store.form.kinozal_mirrors, domain];
    // Если активного зеркала нет (или оно не из списка) — активируем новое.
    if (!store.form.kinozal_mirrors.includes(store.form.kinozal_domain)) {
      store.form.kinozal_domain = domain;
    }
    addMirrorOpen = false;
    store.markDirty();
  };

  const removeSelectedMirror = () => {
    const selected = store.form.kinozal_domain;
    if (!selected || !store.form.kinozal_mirrors.includes(selected)) return;
    const index = store.form.kinozal_mirrors.indexOf(selected);
    const next = store.form.kinozal_mirrors.filter((m) => m !== selected);
    store.form.kinozal_mirrors = next;
    // Удаляем активное зеркало — активируем следующее за ним (иначе первое).
    const nextActive = next[index] ?? next[0] ?? "";
    store.form.kinozal_domain = nextActive;
    toast.success(
      nextActive
        ? `Зеркало ${selected} удалено. Активное зеркало: ${nextActive}.`
        : `Зеркало ${selected} удалено. Активных зеркал не осталось.`
    );
    store.markDirty();
  };
</script>

<div class="space-y-5">
  <div class="grid gap-4 md:grid-cols-2">
    <div class="space-y-2">
      <div class="text-sm font-medium">Зеркала kinozal</div>
      <div class="flex gap-2">
        <Select.Root
          type="single"
          bind:value={store.form.kinozal_domain}
          disabled={!store.form.kinozal_mirrors.length}
          onValueChange={() => store.markDirty()}
        >
          <Select.Trigger class="flex-1" aria-label="Активное зеркало kinozal">
            {#if store.form.kinozal_domain}
              {store.form.kinozal_domain}
            {:else}
              <span class="text-muted-foreground">
                {store.form.kinozal_mirrors.length ? "Выберите зеркало" : "Зеркала не заданы"}
              </span>
            {/if}
          </Select.Trigger>
          <Select.Content>
            {#each store.form.kinozal_mirrors as mirror (mirror)}
              <Select.Item value={mirror}>{mirror}</Select.Item>
            {/each}
          </Select.Content>
        </Select.Root>
        <Button
          variant="outline"
          size="icon"
          onclick={() => (addMirrorOpen = true)}
          disabled={store.form.kinozal_mirrors.length >= MAX_KINOZAL_MIRRORS}
          title="Добавить зеркало"
        >
          <PlusIcon class="h-4 w-4" />
        </Button>
        <Button
          variant="outline"
          size="icon"
          onclick={removeSelectedMirror}
          disabled={!store.form.kinozal_mirrors.includes(store.form.kinozal_domain)}
          title="Удалить выбранное зеркало"
        >
          <MinusIcon class="h-4 w-4" />
        </Button>
      </div>
    </div>
    <div class="space-y-2">
      <div class="text-sm font-medium">Cookie UID</div>
      <Input bind:value={store.form.cookie_uid} placeholder="uid" />
    </div>
    <div class="space-y-2">
      <div class="text-sm font-medium">Cookie PASS</div>
      <Input bind:value={store.form.cookie_pass} type="text" placeholder="pass" />
    </div>
    <div class="space-y-2">
      <div class="text-sm font-medium">Last scan</div>
      <Input bind:value={store.form.last_scan} type="date" />
    </div>
    <div class="space-y-2 md:col-span-2">
      <div class="text-sm font-medium">Последняя успешно обработанная раздача (checkpoint)</div>
      <Input
        value={store.preferences?.last_scan_kinozal_id?.toString() ?? "Не задан"}
        readonly
        aria-label="ID последней успешно обработанной раздачи"
      />
      {#if store.preferences?.last_scan_kinozal_id != null && checkpointUrl}
        <a
          href={checkpointUrl}
          target="_blank"
          rel="noreferrer"
          class="text-primary text-sm underline underline-offset-4"
        >
          Открыть эту раздачу на Kinozal
        </a>
      {:else if store.preferences?.last_scan_kinozal_id != null}
        <p class="text-muted-foreground text-sm">
          Выберите активное зеркало Kinozal, чтобы открыть эту раздачу.
        </p>
      {:else}
        <p class="text-muted-foreground text-sm">Контрольная раздача ещё не сохранена.</p>
      {/if}
    </div>
  </div>

  <Separator />

  <div class="space-y-4">
    <div class="space-y-1">
      <div class="text-sm font-semibold">Автосканирование Kinozal</div>
      <div class="text-muted-foreground text-xs">
        Запуск сканирования по расписанию в фоновом воркере (HUEY). Требует запущенного воркера.
      </div>
    </div>

    <div class="border-border/70 flex items-center justify-between rounded-xl border px-4 py-3">
      <div class="space-y-1">
        <Label for="scan-schedule-enabled" class="text-sm font-medium">
          Автосканирование по расписанию
        </Label>
        <div class="text-muted-foreground text-xs">
          Вкл — скан запускается автоматически с заданным интервалом. Выкл — только вручную.
        </div>
        {#if scanScheduleLocked}
          <div class="text-xs text-amber-600 dark:text-amber-400">
            На этом компьютере автосканирование принудительно отключено в settings
            (KINOZAL_AUTOSCAN_DISABLED).
          </div>
        {/if}
      </div>
      <Switch
        id="scan-schedule-enabled"
        bind:checked={store.form.scan_schedule_enabled}
        disabled={scanScheduleLocked}
        onCheckedChange={(v) => {
          store.form.scan_schedule_enabled = v;
          store.markDirty();
          return v;
        }}
      />
    </div>

    <div class="space-y-2">
      <div class="text-sm font-medium">Интервал, минут</div>
      <Input
        bind:value={store.form.scan_interval_minutes}
        type="number"
        min={MIN_SCAN_INTERVAL_MINUTES}
        disabled={!store.form.scan_schedule_enabled}
      />
      <div class="text-muted-foreground text-xs">
        Минимум {MIN_SCAN_INTERVAL_MINUTES} минут. Интервал считается от завершения предыдущего запуска.
      </div>
    </div>

    <div class="border-border/70 rounded-xl border px-4 py-3 text-sm">
      <div class="flex items-center justify-between">
        <span class="text-muted-foreground">Последний плановый запуск</span>
        <span>{lastScheduledRunLabel}</span>
      </div>
      <div class="mt-1 flex items-center justify-between">
        <span class="text-muted-foreground">Статус</span>
        <span>{lastScheduledStatusLabel}</span>
      </div>
    </div>
  </div>

  <KinozalMirrorDialog
    bind:open={addMirrorOpen}
    existing={store.form.kinozal_mirrors}
    onadd={handleAddMirror}
    oncancel={() => (addMirrorOpen = false)}
  />
</div>
