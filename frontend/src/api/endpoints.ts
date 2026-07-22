/** Endpoint definitions — the only place URL paths appear. */

import type {
  FleetAssetView,
  HealthResponse,
  HostInventoryRecord,
  MissionView,
  ObservatoryEvent,
  TelemetrySnapshot,
} from "@/types";

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

/** Query options for the events read route (all optional, exact-match filters). */
export interface ListEventsParams {
  collectorId?: string;
  eventType?: string;
  /** 1–500; the backend defaults to 100. */
  limit?: number;
}

/**
 * GET /api/v1/events — recent telemetry events, newest first (M004 PR3).
 * The timeline fetches one bounded page and filters client-side, so chip
 * toggles are instant and a single poll serves every filter combination.
 */
export function listEvents(
  params: ListEventsParams = {},
  signal?: AbortSignal,
): Promise<ObservatoryEvent[]> {
  const query = new URLSearchParams();
  if (params.collectorId) query.set("collector_id", params.collectorId);
  if (params.eventType) query.set("event_type", params.eventType);
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return apiFetch<ObservatoryEvent[]>(`/api/v1/events${suffix}`, { signal });
}

/**
 * GET /api/v1/fleet/{fleetId}/docker-status — newest docker_status telemetry
 * for one host (M004 PR3). 404 is a *normal* condition: unknown fleet id or
 * "no docker telemetry reported yet" — callers branch on it, never retry.
 */
export function getDockerStatus(fleetId: string, signal?: AbortSignal): Promise<TelemetrySnapshot> {
  return apiFetch<TelemetrySnapshot>(`/api/v1/fleet/${encodeURIComponent(fleetId)}/docker-status`, {
    signal,
  });
}

/** Authenticated probe used by the Settings connection test (SD-017 key check). */
export function probeAuthenticated(apiKey: string, signal?: AbortSignal): Promise<MissionView[]> {
  return apiFetch<MissionView[]>("/api/v1/missions", { apiKey, signal });
}
