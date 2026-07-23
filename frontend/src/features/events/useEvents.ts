/**
 * Events timeline query (mission §6 auto-refresh): one bounded page of the
 * newest events, polled every 15 s. Chip filtering happens client-side on
 * this single cached page, so toggles are instant and every filter
 * combination shares one poll — the lightest load on the Pi.
 */
import { useQuery } from "@tanstack/react-query";

import { listEvents } from "@/api/endpoints";
import { POLL_INTERVALS } from "@/api/queryClient";
import { queryKeys } from "@/api/queryKeys";

/** One page is plenty for an operational timeline; history is out of scope. */
export const EVENTS_PAGE_SIZE = 200;

export function useEvents() {
  return useQuery({
    queryKey: queryKeys.events,
    queryFn: ({ signal }) => listEvents({ limit: EVENTS_PAGE_SIZE }, signal),
    refetchInterval: POLL_INTERVALS.events,
  });
}
