/** Endpoint definitions — the only place URL paths appear. */

import type { FleetAssetView, HealthResponse, HostInventoryRecord, MissionView } from "@/types";

import { apiFetch } from "./client";

/** GET /health — unauthenticated (SD-013); doubles as the reachability probe. */
export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health", { signal });
}

/** GET /api/v1/fleet — every registry asset with derived connectivity/health. */
export function listFleet(signal?: AbortSignal): Promise<FleetAssetView[]> {
  return apiFetch<FleetAssetView[]>("/api/v1/fleet", { signal });
}

/** GET /api/v1/fleet/{fleetId} — one registry asset (404 when unknown). */
export function getFleetAsset(fleetId: string, signal?: AbortSignal): Promise<FleetAssetView> {
  return apiFetch<FleetAssetView>(`/api/v1/fleet/${encodeURIComponent(fleetId)}`, { signal });
}

/**
 * GET /api/v1/fleet/{fleetId}/inventory — latest Host Inventory projection
 * (M003.5). 404 when the Fleet ID is unknown *or* the host has not reported
 * inventory yet — callers must treat 404 as "no inventory", not as failure.
 */
export function getHostInventory(
  fleetId: string,
  signal?: AbortSignal,
): Promise<HostInventoryRecord> {
  return apiFetch<HostInventoryRecord>(`/api/v1/fleet/${encodeURIComponent(fleetId)}/inventory`, {
    signal,
  });
}

/** GET /api/v1/missions — every tracked mission with lifecycle state. */
export function listMissions(signal?: AbortSignal): Promise<MissionView[]> {
  return apiFetch<MissionView[]>("/api/v1/missions", { signal });
}

/** Authenticated probe used by the Settings connection test (SD-017 key check). */
export function probeAuthenticated(apiKey: string, signal?: AbortSignal): Promise<MissionView[]> {
  return apiFetch<MissionView[]>("/api/v1/missions", { apiKey, signal });
}
