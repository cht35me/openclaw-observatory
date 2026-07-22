import type { FleetAssetView, HealthResponse, MissionView } from "@/types";

export const healthFixture: HealthResponse = {
  status: "ok",
  version: "v0.3.1", // live /health includes the tag prefix, e.g. "v0.3.1"
  uptime_seconds: 93_784,
  database: { connected: true },
};

export function makeAsset(overrides: Partial<FleetAssetView> = {}): FleetAssetView {
  return {
    fleet_id: "RPSG01",
    asset_type: "node",
    nickname: "Singapore Pi",
    hostname: "raspberrypi-sg01",
    role: "edge-node",
    location: "Singapore",
    platform: "Raspberry Pi 5",
    os: "Raspberry Pi OS (Trixie)",
    software_version: null,
    host_fleet_id: null,
    deployment_role: null,
    service_version: null,
    capabilities: ["telemetry", "heartbeat"],
    tags: ["production", "singapore"],
    status: "Active",
    environment: "Production",
    registered_at: "2026-07-20T00:00:00Z",
    updated_at: "2026-07-22T00:00:00Z",
    last_heartbeat: {
      timestamp: "2026-07-22T04:59:00Z",
      received_at: "2026-07-22T04:59:01Z",
      software_version: "0.3.1",
      collector_version: "0.3.1",
      collector_type: "host",
      schema_version: 1,
    },
    connectivity: "online",
    health: "Healthy",
    ...overrides,
  };
}

export const fleetFixture: FleetAssetView[] = [
  makeAsset(),
  makeAsset({
    fleet_id: "OBLN01",
    asset_type: "service",
    nickname: "Observatory Local",
    hostname: "raspberrypi-sg01",
    role: "observatory",
    host_fleet_id: "RPSG01",
    deployment_role: "local",
    service_version: "v1",
  }),
  makeAsset({
    fleet_id: "A001",
    asset_type: "agent",
    nickname: "VeritaUX",
    role: "engineering-agent",
    connectivity: "unknown",
    health: "Unknown",
    last_heartbeat: null,
  }),
];

export function makeMission(overrides: Partial<MissionView> = {}): MissionView {
  return {
    mission_id: "M004",
    title: "Observatory Visibility & Frontend",
    assigned_agent: "A001",
    state: "Running",
    created_at: "2026-07-22T00:00:00Z",
    started_at: "2026-07-22T01:00:00Z",
    completed_at: null,
    duration_seconds: null,
    pr_ref: null,
    commit_sha: null,
    updated_at: "2026-07-22T02:00:00Z",
    ...overrides,
  };
}
