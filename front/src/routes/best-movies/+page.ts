import type { PageLoad } from "./$types";
import type { BestfilmsofFilters } from "$lib/bestfilmsof";

export const load: PageLoad = async ({ fetch }) => {
  try {
    const response = await fetch("/api/bestfilmsof/filters");
    if (!response.ok) {
      let detail = `API error: ${response.status}`;
      try {
        const payload = (await response.json()) as { detail?: string };
        if (payload.detail?.trim()) {
          detail = payload.detail.trim();
        }
      } catch {
        // ignore non-json payloads
      }
      return { filters: null as BestfilmsofFilters | null, apiError: detail };
    }

    return {
      filters: (await response.json()) as BestfilmsofFilters,
      apiError: ""
    };
  } catch (error) {
    return {
      filters: null as BestfilmsofFilters | null,
      apiError: error instanceof Error ? error.message : "Unknown API error"
    };
  }
};
