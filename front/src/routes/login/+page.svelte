<script lang="ts">
  import { goto, invalidateAll } from "$app/navigation";
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Input } from "$lib/components/ui/input";

  let { data } = $props();

  let username = $state("");
  let password = $state("");
  let isSubmitting = $state(false);

  $effect(() => {
    if (data.auth?.is_authenticated) {
      void goto("/");
    }
  });

  const submit = async () => {
    isSubmitting = true;

    try {
      const formData = new FormData();
      formData.set("username", username);
      formData.set("password", password);

      const response = await fetch("/api/auth/login", {
        method: "POST",
        body: formData
      });

      const payload = (await response.json()) as {
        message?: string;
        is_authenticated?: boolean;
      };

      if (!response.ok || !payload.is_authenticated) {
        toast.error(payload.message ?? `HTTP ${response.status}`);
        return;
      }

      await invalidateAll();
      await goto("/");
      toast.success(payload.message ?? "Вход выполнен.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Ошибка входа");
    } finally {
      isSubmitting = false;
    }
  };
</script>

<div class="flex min-h-[calc(100vh-3.5rem)] items-center justify-center p-6">
  <Card class="w-full max-w-md rounded-2xl border-border/70 bg-card/90 shadow-sm">
    <CardHeader class="space-y-2">
      <CardTitle class="text-2xl">Вход</CardTitle>
      <CardDescription>
        Django session остаётся на backend, а интерфейс логина живёт целиком в Svelte.
      </CardDescription>
    </CardHeader>
    <CardContent>
      <form class="space-y-4" onsubmit={(event) => {
        event.preventDefault();
        void submit();
      }}>
        <Input bind:value={username} name="username" placeholder="Username" autocomplete="username" />
        <Input
          bind:value={password}
          name="password"
          type="password"
          placeholder="Password"
          autocomplete="current-password"
        />
        <Button class="w-full" type="submit" disabled={isSubmitting || !username.trim() || !password}>
          {isSubmitting ? "Входим..." : "Войти"}
        </Button>
      </form>
    </CardContent>
  </Card>
</div>
