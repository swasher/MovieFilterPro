<div class="mx-auto w-full max-w-6xl p-6">
  <div class="mb-6 space-y-2">
    <h1 class="text-2xl font-semibold">Front Template</h1>
    <p class="text-sm text-muted-foreground">
      Базовый каркас страницы: общий layout, header с кнопками и sidebar без ручной сортировки.
    </p>
  </div>

  <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
    {#each Array.from({ length: 6 }) as _, index (index)}
      <article class="rounded-xl border bg-card p-4 text-card-foreground shadow-sm">
        <h2 class="mb-2 text-base font-medium">Карточка {index + 1}</h2>
        <p class="text-sm text-muted-foreground">Здесь будет контент нового проекта.</p>
      </article>
    {/each}
  </div>
</div>
