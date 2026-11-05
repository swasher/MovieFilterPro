<script lang="ts">
  import AppShell from "$lib/components/AppShell.svelte";
  import { headerLinks } from "$lib/template-data";
  import { Toaster } from "$lib/components/ui/sonner";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import "./layout.css";

  let { children, data } = $props();
</script>

<Toaster position="top-center" />
{#if data.auth?.users_exist === false}
  <div class="bg-background flex min-h-svh items-center justify-center p-6">
    <Card class="w-full max-w-xl rounded-2xl border-border/70 bg-card/90 shadow-sm">
      <CardHeader class="space-y-2">
        <CardTitle class="text-2xl">База данных ещё не настроена</CardTitle>
        <CardDescription>
          В системе нет ни одного пользователя, поэтому войти пока невозможно.
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-4 text-sm">
        <p class="text-muted-foreground">
          Создайте суперпользователя на сервере, выполнив команду в каталоге приложения:
        </p>
        <pre class="bg-muted overflow-x-auto rounded-lg px-4 py-3"><code>uv run python manage.py createsuperuser</code></pre>
        <p class="text-muted-foreground">
          После создания пользователя обновите эту страницу и войдите в систему.
        </p>
      </CardContent>
    </Card>
  </div>
{:else}
  <AppShell {headerLinks} auth={data.auth} siteVersion={data.siteVersion} appName="MovieFilter Pro">
    {@render children?.()}
  </AppShell>
{/if}
