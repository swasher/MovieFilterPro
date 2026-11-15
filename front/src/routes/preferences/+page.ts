import type { PageLoad } from "./$types";
import { type PreferencesApiErrorPayload, type PreferencesData } from "$lib/preferences";
import type { TasteProfile } from "$lib/aiPredict";

type TasteProfilesResult = {
  tastes: TasteProfile[];
  tastesError: string;
};

async function loadTasteProfiles(fetch: typeof window.fetch): Promise<TasteProfilesResult> {
  try {
    const response = await fetch("/api/ai-predict/tastes");
    if (!response.ok) {
      return { tastes: [], tastesError: `API error: ${response.status}` };
    }
    return { tastes: (await response.json()) as TasteProfile[], tastesError: "" };
  } catch (error) {
    return {
      tastes: [],
      tastesError: error instanceof Error ? error.message : "Unknown API error"
    };
  }
}

export const load: PageLoad = async ({ fetch }) => {
  const tasteProfiles = await loadTasteProfiles(fetch);

  try {
    const response = await fetch("/api/core/preferences");

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
        apiError: detail,
        ...tasteProfiles
      };
    }

    return {
      preferences: (await response.json()) as PreferencesData,
      apiError: "",
      ...tasteProfiles
    };
  } catch (error) {
    return {
      preferences: null,
      apiError: error instanceof Error ? error.message : "Unknown API error",
      ...tasteProfiles
    };
  }
};
