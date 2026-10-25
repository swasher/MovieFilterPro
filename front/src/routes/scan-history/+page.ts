import type { PageLoad } from "./$types";

export type ApiScanRun = {
  id: number;
  trigger: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  scan_to_date: string | null;
  new_movies_count: number;
  error_type: string | null;
  error_message: string;
  entries_count: number;
};

export type ApiScanLogEntry = {
  id: number;
  level: string;
  message: string;
  created_at: string | null;
};

export const load: PageLoad = async ({ fetch }) => {
  try {
    const response = await fetch("/api/kinozal/scan/history?limit=100");
    if (!response.ok) {
      return {
        runs: [] as ApiScanRun[],
        apiError: `API error: ${response.status}`
      };
    }
    const payload = (await response.json()) as { items?: ApiScanRun[] };
    return {
      runs: payload.items ?? [],
      apiError: ""
    };
  } catch (error) {
    return {
      runs: [] as ApiScanRun[],
      apiError: error instanceof Error ? error.message : "Unknown API error"
    };
  }
};
