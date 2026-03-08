import type { PageLoad } from "./$types";
import {
  DEFAULT_PRIORITY_FILTER,
  DEFAULT_REVERSE,
  DEFAULT_SORT_KEY,
  KINOZAL_PAGE_SIZE,
  emptyKinozalMoviesPage,
  emptyKinozalSummary,
  type KinozalPriorityFilter,
  type KinozalSortKey,
  type KinozalSummary,
  type KinozalMoviesPage
} from "$lib/kinozal";

const validPriorities = new Set([
  "ALL",
  "HIGH",
  "LOW",
  "DEFER",
  "SKIP",
  "WAIT_TRANS",
  "TRANS_FOUND"
] as const);

const validSorts = new Set([
  "date_added",
  "title",
  "year",
  "imdb_rating",
  "kinopoisk_rating"
] as const);

export const load: PageLoad = async ({ fetch, url }) => {
  try {
    const priorityParam = (url.searchParams.get("priority") ?? DEFAULT_PRIORITY_FILTER).trim().toUpperCase();
    const activePriority = (
      validPriorities.has(priorityParam as KinozalPriorityFilter) ? priorityParam : DEFAULT_PRIORITY_FILTER
    ) as KinozalPriorityFilter;
    const q = (url.searchParams.get("q") ?? "").trim();
    const sortParam = (url.searchParams.get("sort") ?? DEFAULT_SORT_KEY).trim();
    const activeSort = (
      validSorts.has(sortParam as KinozalSortKey) ? sortParam : DEFAULT_SORT_KEY
    ) as KinozalSortKey;
    const reverseParam = (url.searchParams.get("reverse") ?? "").trim().toLowerCase();
    const activeReverse = reverseParam === "true";

    const movieParams = new URLSearchParams({ limit: String(KINOZAL_PAGE_SIZE) });
    if (activePriority !== "ALL") {
      movieParams.set("priority", activePriority);
    }
    if (q) {
      movieParams.set("q", q);
    }
    if (activeSort !== DEFAULT_SORT_KEY) {
      movieParams.set("sort", activeSort);
    }
    if (activeReverse !== DEFAULT_REVERSE) {
      movieParams.set("reverse", "true");
    }

    const [pageResponse, summaryResponse] = await Promise.all([
      fetch(`/api/kinozal/movies?${movieParams.toString()}`),
      fetch("/api/kinozal/summary")
    ]);

    if (!pageResponse.ok) {
      let detail = `API error: ${pageResponse.status}`;

      try {
        const payload = (await pageResponse.json()) as { detail?: string };
        if (payload.detail?.trim()) {
          detail = payload.detail.trim();
        }
      } catch {
        // ignore non-json payloads
      }

      return {
        page: emptyKinozalMoviesPage(),
        summary: emptyKinozalSummary(),
        apiError: detail,
        summaryError: "",
        activePriority,
        activeQuery: q,
        activeSort,
        activeReverse
      };
    }

    let summary = emptyKinozalSummary();
    let summaryError = "";

    if (summaryResponse.ok) {
      summary = (await summaryResponse.json()) as KinozalSummary;
    } else {
      try {
        const payload = (await summaryResponse.json()) as { detail?: string };
        summaryError = payload.detail?.trim() || `Summary API error: ${summaryResponse.status}`;
      } catch {
        summaryError = `Summary API error: ${summaryResponse.status}`;
      }
    }

    return {
      page: (await pageResponse.json()) as KinozalMoviesPage,
      summary,
      apiError: "",
      summaryError,
      activePriority,
      activeQuery: q,
      activeSort,
      activeReverse
    };
  } catch (error) {
    return {
      page: emptyKinozalMoviesPage(),
      summary: emptyKinozalSummary(),
      apiError: error instanceof Error ? error.message : "Unknown API error",
      summaryError: "",
      activePriority: DEFAULT_PRIORITY_FILTER as KinozalPriorityFilter,
      activeQuery: "",
      activeSort: DEFAULT_SORT_KEY as KinozalSortKey,
      activeReverse: DEFAULT_REVERSE
    };
  }
};
