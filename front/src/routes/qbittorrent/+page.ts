import type { PageLoad } from "./$types";
import {
  parseQbtApiError,
  type QbtApiErrorDetail,
  type QbtTorrent,
  type QbtTorrentsResponse
} from "$lib/qbittorrent";

const EMPTY_ERROR: QbtApiErrorDetail = { message: "" };

export const load: PageLoad = async ({ fetch }) => {
  try {
    const response = await fetch("/api/qbittorrent/torrents?limit=500");
    const payload = await response.json();

    if (!response.ok) {
      const error = parseQbtApiError(payload, `HTTP ${response.status}`);
      return {
        items: [] as QbtTorrent[],
        total: 0,
        apiError: error as QbtApiErrorDetail,
        unconfigured:
          error.code === "qbt_not_configured" ||
          error.code === "qbt_auth_failed" ||
          error.code === "qbt_invalid_url" ||
          error.code === "qbt_unreachable" ||
          error.code === "qbt_forbidden" ||
          error.code === "qbt_unauthorized"
      };
    }

    const data = payload as QbtTorrentsResponse;
    return {
      items: data.items ?? [],
      total: data.total ?? 0,
      apiError: EMPTY_ERROR,
      unconfigured: false
    };
  } catch (error) {
    return {
      items: [] as QbtTorrent[],
      total: 0,
      apiError: {
        message: error instanceof Error ? error.message : "Не удалось загрузить список раздач."
      } as QbtApiErrorDetail,
      unconfigured: false
    };
  }
};
