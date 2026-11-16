import type { PageLoad } from "./$types";
import { type PreferencesApiErrorPayload, type PreferencesData } from "$lib/preferences";
import type { AiEndpoint } from "$lib/aiEndpoints";
import type { TasteProfile } from "$lib/aiPredict";

type TasteProfilesResult = {
  tastes: TasteProfile[];
  tastesError: string;
};

type AiEndpointsResult = {
  endpoints: AiEndpoint[];
  endpointsError: string;
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

async function loadAiEndpoints(fetch: typeof window.fetch): Promise<AiEndpointsResult> {
  try {
    const response = await fetch("/api/core/ai-endpoints");
    if (!response.ok) {
      return { endpoints: [], endpointsError: `API error: ${response.status}` };
    }
    return { endpoints: (await response.json()) as AiEndpoint[], endpointsError: "" };
  } catch (error) {
    return {
      endpoints: [],
      endpointsError: error instanceof Error ? error.message : "Unknown API error"
    };
  }
}

export const load: PageLoad = async ({ fetch }) => {
  const tasteProfiles = await loadTasteProfiles(fetch);
  const aiEndpoints = await loadAiEndpoints(fetch);

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
        ...tasteProfiles,
        ...aiEndpoints
      };
    }

    return {
      preferences: (await response.json()) as PreferencesData,
      apiError: "",
      ...tasteProfiles,
      ...aiEndpoints
    };
  } catch (error) {
    return {
      preferences: null,
      apiError: error instanceof Error ? error.message : "Unknown API error",
      ...tasteProfiles,
      ...aiEndpoints
    };
  }
};
