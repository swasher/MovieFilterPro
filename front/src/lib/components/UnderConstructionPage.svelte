<script lang="ts">
  import { Button } from "$lib/components/ui/button";
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "$lib/components/ui/card";

  type Props = {
    title: string;
    description: string;
    targetLabel: string;
    targetHref: string;
  };

  let { title, description, targetLabel, targetHref }: Props = $props();
</script>

<div class="flex min-h-[calc(100vh-3.5rem)] items-center justify-center p-6">
  <Card class="w-full max-w-3xl rounded-3xl border-border/70 bg-card/95 shadow-sm">
    <CardHeader class="space-y-4 text-center">
      <p class="text-primary text-4xl font-black tracking-[0.24em]">UNDER CONSTRUCTION</p>
      <CardTitle class="text-3xl">{title}</CardTitle>
      <CardDescription class="mx-auto max-w-2xl text-base">
        {description}
      </CardDescription>
    </CardHeader>
    <CardContent class="flex justify-center">
      <Button href={targetHref} variant="outline" size="lg">
        {targetLabel}
      </Button>
    </CardContent>
  </Card>
</div>
