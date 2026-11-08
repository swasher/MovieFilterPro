<script lang="ts">
  import { goto } from "$app/navigation";
  import LoginForm from "$lib/components/LoginForm.svelte";

  let { data } = $props();

  $effect(() => {
    if (data.auth?.is_authenticated) {
      void goto("/");
    }
  });
</script>

<LoginForm siteVersion={data.siteVersion} />
