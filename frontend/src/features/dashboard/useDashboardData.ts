import { useQuery } from "@tanstack/react-query";

import { listFleet, listMissions } from "@/api/endpoints";
import { POLL_INTERVALS } from "@/api/queryClient";
import { queryKeys } from "@/api/queryKeys";
import type { Connectivity, FleetAssetView, HealthStatus, MissionView } from "@/types";

export function useFleet() {
  return useQuery({
    queryKey: queryKeys.fleet,
    queryFn: ({ signal }) => listFleet(signal),
    refetchInterval: POLL_INTERVALS.fleet,
  });
}

export function useMissions() {
  return useQuery({
    queryKey: queryKeys.missions,
    queryFn: ({ signal }) => listMissions(signal),
    refetchInterval: POLL_INTERVALS.missions,
  });
}

/**
 * The mission currently in flight: the most recently updated mission that is
 * not Completed. Missions are a linear lifecycle (M003 §4), so at current
 * fleet size this is "the active mission".
 */
export function selectActiveMission(missions: MissionView[]): MissionView | null {
  const active = missions
    .filter((mission) => mission.state !== "Completed")
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  return active[0] ?? null;
}

export interface FleetSummary {
  total: number;
  byType: { nodes: number; services: number; agents: number; other: number };
  connectivity: Record<Connectivity, number>;
  health: Record<HealthStatus, number>;
}

export function summarizeFleet(assets: FleetAssetView[]): FleetSummary {
  const summary: FleetSummary = {
    total: assets.length,
    byType: { nodes: 0, services: 0, agents: 0, other: 0 },
    connectivity: { online: 0, offline: 0, unknown: 0 },
    health: { Healthy: 0, Warning: 0, Critical: 0, Offline: 0, Unknown: 0 },
  };
  for (const asset of assets) {
    if (asset.asset_type === "node") summary.byType.nodes += 1;
    else if (asset.asset_type === "service") summary.byType.services += 1;
    else if (asset.asset_type === "agent") summary.byType.agents += 1;
    else summary.byType.other += 1;
    summary.connectivity[asset.connectivity] += 1;
    summary.health[asset.health] += 1;
  }
  return summary;
}

/**
 * Deployment environment shown on the dashboard: the environment of the
 * Observatory *service* asset (the deployment itself, e.g. OBLN01), which is
 * the SD-001 anchor for "what am I looking at". Null when the registry has
 * no service asset yet.
 */
export function selectObservatoryEnvironment(assets: FleetAssetView[]): string | null {
  const observatory = assets.find(
    (asset) => asset.asset_type === "service" && asset.deployment_role !== null,
  );
  return observatory?.environment ?? null;
}
