export type TasteProfile = {
  id: number;
  name: string;
  content: string;
  updated_at: string;
};

export type PredictionStatus = "running" | "done" | "error";

export type PredictionSource = "vault" | "kinozal";

export type AiPrediction = {
  id: number;
  source: PredictionSource;
  movie_id: number | null;
  rss_movie_id: number | null;
  movie_title: string;
  taste_profile_id: number | null;
  taste_profile_name: string | null;
  status: PredictionStatus;
  status_display: string;
  score: number | null;
  verdict: "watch" | "maybe" | "skip" | null;
  verdict_display: string | null;
  confidence: number | null;
  result_text: string;
  error: string;
  model_name: string;
  duration_ms: number | null;
  created_at: string;
};

const BASE_URL = "/api/ai-predict";
const TASTE_STORAGE_KEY = "moviefilter:ai-taste-id";

type ApiErrorPayload = { detail?: string };

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });

  if (!response.ok) {
    let detail = `Ошибка API: ${response.status}`;
    try {
      const payload = (await response.json()) as ApiErrorPayload;
      if (payload.detail?.trim()) {
        detail = payload.detail.trim();
      }
    } catch {
      // не-JSON ответ — оставляем код статуса
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

export function listTasteProfiles(): Promise<TasteProfile[]> {
  return apiRequest<TasteProfile[]>("/tastes");
}

export function createTasteProfile(name: string, content: string): Promise<TasteProfile> {
  return apiRequest<TasteProfile>("/tastes", {
    method: "POST",
    body: JSON.stringify({ name, content })
  });
}

export function updateTasteProfile(
  id: number,
  payload: { name?: string; content?: string }
): Promise<TasteProfile> {
  return apiRequest<TasteProfile>(`/tastes/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export function deleteTasteProfile(id: number): Promise<{ ok: boolean }> {
  return apiRequest<{ ok: boolean }>(`/tastes/${id}`, { method: "DELETE" });
}

export function runPrediction(movieId: number, tasteProfileId: number | null): Promise<AiPrediction> {
  return apiRequest<AiPrediction>("/predict", {
    method: "POST",
    body: JSON.stringify({ movie_id: movieId, taste_profile_id: tasteProfileId })
  });
}

export function runKinozalPrediction(
  rssMovieId: number,
  tasteProfileId: number | null
): Promise<AiPrediction> {
  return apiRequest<AiPrediction>("/kinozal/predict", {
    method: "POST",
    body: JSON.stringify({ rss_movie_id: rssMovieId, taste_profile_id: tasteProfileId })
  });
}

export async function fetchLastPrediction(
  movieId: number,
  tasteProfileId: number | null
): Promise<AiPrediction | null> {
  const params = new URLSearchParams({ movie_id: String(movieId) });
  if (tasteProfileId !== null) {
    params.set("taste_profile_id", String(tasteProfileId));
  }
  const payload = await apiRequest<{ prediction: AiPrediction | null }>(
    `/predictions/last?${params.toString()}`
  );
  return payload.prediction;
}

export async function fetchLastKinozalPrediction(
  rssMovieId: number,
  tasteProfileId: number | null
): Promise<AiPrediction | null> {
  const params = new URLSearchParams({ rss_movie_id: String(rssMovieId) });
  if (tasteProfileId !== null) {
    params.set("taste_profile_id", String(tasteProfileId));
  }
  const payload = await apiRequest<{ prediction: AiPrediction | null }>(
    `/kinozal/predictions/last?${params.toString()}`
  );
  return payload.prediction;
}

// Последний выбранный профиль вкусов — общий для Preferences и страницы фильма.
export function getPreferredTasteId(): number | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(TASTE_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

export function setPreferredTasteId(id: number | null): void {
  if (typeof window === "undefined") {
    return;
  }
  if (id === null) {
    window.localStorage.removeItem(TASTE_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(TASTE_STORAGE_KEY, String(id));
}

export function resolveTasteProfile(
  profiles: TasteProfile[],
  preferredId: number | null
): TasteProfile | null {
  if (!profiles.length) {
    return null;
  }
  return profiles.find((profile) => profile.id === preferredId) ?? profiles[0];
}

export function predictionScoreLabel(prediction: AiPrediction): string {
  if (prediction.score === null) {
    return "—";
  }
  return `${prediction.score}/10`;
}

// --- Системный промпт (общая методика, без предпочтений конкретного человека) ---

export type PromptState = {
  content: string;
  default_content: string;
  is_default: boolean;
  updated_at: string | null;
};

export function fetchPromptState(): Promise<PromptState> {
  return apiRequest<PromptState>("/prompt");
}

export function savePromptState(content: string): Promise<PromptState> {
  return apiRequest<PromptState>("/prompt", {
    method: "PUT",
    body: JSON.stringify({ content })
  });
}

export function resetPromptState(): Promise<PromptState> {
  return apiRequest<PromptState>("/prompt/reset", {
    method: "POST",
    body: JSON.stringify({})
  });
}
