import type { PageLoad } from "./$types";
import { type PreferencesApiErrorPayload, type PreferencesData } from "$lib/preferences";

export const load: PageLoad = async ({ fetch }) => {
  try {
    const response = await fetch("/api/preferences");

    if (!response.ok) {
      let detail = `API error: ${response.status}`;

      try {
        const payload = (await response.json()) as PreferencesApiErrorPayload;
        if (payload.detail?.trim()) {
          detail = payload.detail.trim();
        }
      } catch {
        // ignore non-json payloads
      }

      return {
        preferences: null,
        apiError: detail
      };
    }

    return {
      preferences: (await response.json()) as PreferencesData,
      apiError: ""
    };
  } catch (error) {
    return {
      preferences: null,
      apiError: error instanceof Error ? error.message : "Unknown API error"
    };
  }
};
