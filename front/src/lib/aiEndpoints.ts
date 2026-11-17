export type AiEndpoint = {
  id: number;
  name: string;
  base_url: string;
  model: string;
  has_api_key: boolean;
  api_key_masked: string;
  is_selected: boolean;
  updated_at: string;
};

export type AiEndpointInput = {
  name: string;
  base_url: string;
  model: string;
  /** Только для создания; ключ никогда не приходит с сервера. */
  api_key?: string;
  /** Сразу сделать endpoint выбранным (создание + выбор в одной транзакции). */
  select?: boolean;
  /** Скопировать API-ключ исходного endpoint на сервере (ключ не покидает backend). */
  duplicate_of?: number;
};

export type AiEndpointUpdateInput = {
  name?: string;
  base_url?: string;
  model?: string;
};

const BASE_URL = "/api/core/ai-endpoints";

type ApiErrorPayload = { detail?: string };

async function apiRequest<T>(path = "", init?: RequestInit): Promise<T> {
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

export function listAiEndpoints(): Promise<AiEndpoint[]> {
  return apiRequest<AiEndpoint[]>();
}

export function createAiEndpoint(payload: AiEndpointInput): Promise<AiEndpoint> {
  return apiRequest<AiEndpoint>("", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateAiEndpoint(
  id: number,
  payload: AiEndpointUpdateInput
): Promise<AiEndpoint> {
  return apiRequest<AiEndpoint>(`/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export function deleteAiEndpoint(id: number): Promise<{ ok: boolean }> {
  return apiRequest<{ ok: boolean }>(`/${id}`, { method: "DELETE" });
}

export function selectAiEndpoint(id: number): Promise<AiEndpoint> {
  return apiRequest<AiEndpoint>(`/${id}/select`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function replaceAiEndpointKey(id: number, apiKey: string): Promise<AiEndpoint> {
  return apiRequest<AiEndpoint>(`/${id}/api-key`, {
    method: "PUT",
    body: JSON.stringify({ api_key: apiKey })
  });
}

export function resolveSelectedEndpoint(endpoints: AiEndpoint[]): AiEndpoint | null {
  return endpoints.find((endpoint) => endpoint.is_selected) ?? null;
}
