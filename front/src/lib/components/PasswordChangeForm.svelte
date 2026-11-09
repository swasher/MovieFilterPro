<script lang="ts">
  import { toast } from "svelte-sonner";
  import { Button } from "$lib/components/ui/button";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Input } from "$lib/components/ui/input";
  import { Label } from "$lib/components/ui/label";

  let currentPassword = $state("");
  let newPassword = $state("");
  let confirmPassword = $state("");
  let isSubmitting = $state(false);
  let errorMessage = $state("");

  const canSubmit = $derived(
    !isSubmitting &&
      currentPassword.length > 0 &&
      newPassword.length > 0 &&
      confirmPassword.length > 0
  );

  const submit = async () => {
    errorMessage = "";

    if (newPassword !== confirmPassword) {
      errorMessage = "Пароли не совпадают.";
      return;
    }
    if (newPassword === currentPassword) {
      errorMessage = "Новый пароль должен отличаться от текущего.";
      return;
    }

    isSubmitting = true;
    try {
      const formData = new FormData();
      formData.set("current_password", currentPassword);
      formData.set("new_password", newPassword);

      const response = await fetch("/api/auth/password/", {
        method: "POST",
        body: formData
      });

      const payload = (await response.json().catch(() => ({}))) as {
        message?: string;
      };

      if (!response.ok) {
        errorMessage = payload.message ?? `Не удалось сменить пароль (HTTP ${response.status}).`;
        toast.error(errorMessage);
        return;
      }

      toast.success(payload.message ?? "Пароль изменён.");
      currentPassword = "";
      newPassword = "";
      confirmPassword = "";
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : "Не удалось сменить пароль.";
      toast.error(errorMessage);
    } finally {
      isSubmitting = false;
    }
  };
</script>

<Card id="password" class="scroll-mt-24 border-border/70">
  <CardHeader>
    <CardTitle class="text-xl">Смена пароля</CardTitle>
    <CardDescription>
      Пароль от текущего аккаунта. После смены другие активные сессии этого пользователя будут завершены.
    </CardDescription>
  </CardHeader>
  <CardContent>
    <form
      class="space-y-4"
      onsubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <div class="space-y-2">
        <Label for="password-current" class="text-sm font-medium">Текущий пароль</Label>
        <Input
          id="password-current"
          type="password"
          bind:value={currentPassword}
          autocomplete="current-password"
        />
      </div>

      <div class="space-y-2">
        <Label for="password-new" class="text-sm font-medium">Новый пароль</Label>
        <Input
          id="password-new"
          type="password"
          bind:value={newPassword}
          autocomplete="new-password"
        />
      </div>

      <div class="space-y-2">
        <Label for="password-confirm" class="text-sm font-medium">Повторите новый пароль</Label>
        <Input
          id="password-confirm"
          type="password"
          bind:value={confirmPassword}
          autocomplete="new-password"
        />
      </div>

      {#if errorMessage}
        <p class="text-destructive text-sm">{errorMessage}</p>
      {/if}

      <div class="flex justify-end">
        <Button type="submit" disabled={!canSubmit}>
          {isSubmitting ? "Сохраняем..." : "Сменить пароль"}
        </Button>
      </div>
    </form>
  </CardContent>
</Card>
