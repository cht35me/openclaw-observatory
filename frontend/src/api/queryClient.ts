import { QueryClient } from "@tanstack/react-query";

import { isRetryableError } from "./client";

/** Poll intervals in ms, matched to operational value (frontend-architecture.md §3). */
export const POLL_INTERVALS = {
  health: 30_000,
  fleet: 30_000,
  /** Node details + inventory poll slowly — identity changes rarely (§3). */
  fleetAsset: 60_000,
  inventory: 60_000,
  missions: 60_000,
} as const;

/**
 * One retry/caching policy for the whole app: cached data renders
 * immediately while fresh data is fetched; network/5xx failures retry twice
 * with backoff; 4xx never retries (a 401 will not fix itself).
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failureCount, error) => failureCount < 2 && isRetryableError(error),
        staleTime: 10_000,
        refetchIntervalInBackground: false,
        refetchOnWindowFocus: true,
      },
    },
  });
}
