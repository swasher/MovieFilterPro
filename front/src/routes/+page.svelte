<script lang="ts">
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Button } from "$lib/components/ui/button";

  const cards = Array.from({ length: 6 }, (_, index) => index + 1);
</script>

<div class="mx-auto w-full max-w-6xl p-6">
  <div class="mb-6 space-y-2">
    <h1 class="text-2xl font-semibold">Front Template</h1>
    <p class="text-muted-foreground text-sm">
      Базовый каркас страницы: общий layout, header с кнопками и sidebar без ручной сортировки.
    </p>
  </div>

  <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
    {#each cards as cardNumber (cardNumber)}
      <Card>
        <CardHeader>
          <CardTitle>Карточка {cardNumber}</CardTitle>
          <CardDescription>Здесь будет контент нового проекта.</CardDescription>
        </CardHeader>
        <CardContent class="flex items-center justify-between gap-2">
          <p class="text-muted-foreground text-sm">Черновой блок контента</p>
          <Button size="sm" variant="outline">Open</Button>
        </CardContent>
      </Card>
    {/each}
  </div>
</div>
