export type AiEndpoint = {
  id: number;
  name: string;
  base_url: string;
  model: string;
  api_key: string;
  is_active: boolean;
  updated_at: string;
};

export type AiEndpointInput = {
  name: string;
  base_url: string;
  model: string;
  api_key: string;
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
  payload: Partial<AiEndpointInput>
): Promise<AiEndpoint> {
  return apiRequest<AiEndpoint>(`/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export function deleteAiEndpoint(id: number): Promise<{ ok: boolean }> {
  return apiRequest<{ ok: boolean }>(`/${id}`, { method: "DELETE" });
}

export function activateAiEndpoint(id: number): Promise<AiEndpoint> {
  return apiRequest<AiEndpoint>(`/${id}/activate`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function resolveAiEndpoint(endpoints: AiEndpoint[]): AiEndpoint | null {
  return endpoints.find((endpoint) => endpoint.is_active) ?? null;
}
