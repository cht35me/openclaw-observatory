/**
 * Fleet Registry + Host Inventory queries (docs/frontend-architecture.md §3).
 *
 * Query keys are shared with the dashboard, so navigating Dashboard → Fleet →
 * Node details renders instantly from cache while fresh data loads.
 */
import { useQueries, useQuery } from "@tanstack/react-query";

import { getFleetAsset, getHostInventory, listFleet } from "@/api/endpoints";
import { POLL_INTERVALS } from "@/api/queryClient";
import { queryKeys } from "@/api/queryKeys";
import type { FleetAssetView, HostInventoryRecord } from "@/types";

export function useFleet() {
  return useQuery({
    queryKey: queryKeys.fleet,
    queryFn: ({ signal }) => listFleet(signal),
    refetchInterval: POLL_INTERVALS.fleet,
  });
}

export function useFleetAsset(fleetId: string) {
  return useQuery({
    queryKey: queryKeys.fleetAsset(fleetId),
    queryFn: ({ signal }) => getFleetAsset(fleetId, signal),
    refetchInterval: POLL_INTERVALS.fleetAsset,
  });
}

/**
 * Latest Host Inventory for one node. A 404 means "this asset has not
 * reported inventory" — a normal condition (agents/services never do), so
 * callers must branch on it rather than render a failure.
 */
export function useHostInventory(fleetId: string) {
  return useQuery({
    queryKey: queryKeys.hostInventory(fleetId),
    queryFn: ({ signal }) => getHostInventory(fleetId, signal),
    refetchInterval: POLL_INTERVALS.inventory,
  });
}

/**
 * Inventories for the *node* assets in a fleet list (used by the Fleet cards
 * to show real hardware identity). One request per node, cached under the
 * same keys the node-details page uses — no duplicate traffic.
 */
export function useNodeInventories(
  assets: FleetAssetView[] | undefined,
): Map<string, HostInventoryRecord> {
  const nodes = (assets ?? []).filter((asset) => asset.asset_type === "node");
  const results = useQueries({
    queries: nodes.map((node) => ({
      queryKey: queryKeys.hostInventory(node.fleet_id),
      queryFn: ({ signal }: { signal: AbortSignal }) => getHostInventory(node.fleet_id, signal),
      refetchInterval: POLL_INTERVALS.inventory,
    })),
  });
  const byFleetId = new Map<string, HostInventoryRecord>();
  results.forEach((result, index) => {
    const node = nodes[index];
    if (node && result.data) byFleetId.set(node.fleet_id, result.data);
  });
  return byFleetId;
}
