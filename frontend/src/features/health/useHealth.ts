import { useQuery } from "@tanstack/react-query";

import { isApiRequestError } from "@/api/client";
import { getHealth } from "@/api/endpoints";
import { POLL_INTERVALS } from "@/api/queryClient";
import { queryKeys } from "@/api/queryKeys";

/** Shared /health poll — dashboard cards and the offline banner read the same cache entry. */
export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => getHealth(signal),
    refetchInterval: POLL_INTERVALS.health,
  });
}

/** True when the last /health attempt failed at the network level (backend unreachable). */
export function isBackendUnreachable(error: unknown): boolean {
  return isApiRequestError(error) && error.error.kind === "network";
}
