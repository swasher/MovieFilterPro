export type QbtLinkedMovie = {
  id: number;
  title: string;
  slug: string;
};

export type QbtTorrent = {
  info_hash: string;
  name: string;
  state: string;
  progress: number;
  size: number;
  total_size: number;
  dlspeed: number;
  upspeed: number;
  eta: number;
  category: string;
  tags: string[];
  save_path: string;
  content_path: string;
  added_on: number | null;
  completion_on: number | null;
  linked_movie: QbtLinkedMovie | null;
};

export type QbtTorrentsResponse = {
  items: QbtTorrent[];
  total: number;
  limit: number;
  offset: number;
};

export type QbtApiErrorDetail = {
  code?: string;
  message?: string;
  hint?: string;
};

export type QbtApiErrorPayload = {
  detail?: string | QbtApiErrorDetail;
};

export const parseQbtApiError = (payload: unknown, fallback: string): QbtApiErrorDetail => {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) {
    return { message: fallback };
  }

  const detail = (payload as QbtApiErrorPayload).detail;
  if (!detail) {
    return { message: fallback };
  }

  if (typeof detail === "string") {
    try {
      const parsed = JSON.parse(detail) as QbtApiErrorDetail;
      if (parsed && typeof parsed === "object") return parsed;
    } catch {
      return { message: detail || fallback };
    }
    return { message: detail || fallback };
  }

  return {
    code: detail.code,
    message: detail.message || fallback,
    hint: detail.hint
  };
};
