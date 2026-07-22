/**
 * Services runtime view model (mission §5), derived from the endpoints that
 * exist today: GET /api/v1/fleet (identity, heartbeat, health) and GET
 * /health (backend uptime).
 *
 * Honesty over decoration: restart count, CPU, RAM, and RX/TX exist as
 * docker_status telemetry, and collector process uptime is in heartbeat
 * payloads — but no REST read endpoint exposes either today. Those fields
 * are rendered as "Not reported"; the additive-endpoint proposal lives in
 * the M004 PR2 description.
 */
import type {
  Connectivity,
  FleetAssetView,
  HealthResponse,
  HealthStatus,
  HeartbeatInfo,
} from "@/types";

export type ServiceKind = "backend" | "host-collector" | "agent-collector" | "exporter";

export interface ServiceRuntime {
  id: string;
  kind: ServiceKind;
  name: string;
  /** Where it runs / what it is, e.g. "OBLN01 · raspberrypi-sg01". */
  subtitle: string;
  version: string | null;
  /** Only the backend answering /health reports uptime over REST today. */
  uptimeSeconds: number | null;
  heartbeat: HeartbeatInfo | null;
  connectivity: Connectivity;
  health: HealthStatus;
}

function isExporter(asset: FleetAssetView): boolean {
  const haystack = `${asset.role} ${asset.tags.join(" ")}`.toLowerCase();
  return haystack.includes("exporter");
}

/**
 * Map registry assets onto the four mission service groups. Backend uptime
 * is attached only when the registry holds exactly one backend service
 * asset — /health describes the deployment this console talks to, and with
 * multiple registered backends the match would be a guess, not a fact.
 */
export function deriveServices(
  assets: FleetAssetView[],
  health: HealthResponse | undefined,
): ServiceRuntime[] {
  const services: ServiceRuntime[] = [];
  const backends = assets.filter((a) => a.asset_type === "service" && !isExporter(a));

  for (const asset of backends) {
    services.push({
      id: asset.fleet_id,
      kind: "backend",
      name: asset.role || "Backend",
      subtitle: `${asset.fleet_id} · ${asset.hostname}`,
      version: asset.software_version ?? asset.last_heartbeat?.software_version ?? null,
      uptimeSeconds: backends.length === 1 && health ? health.uptime_seconds : null,
      heartbeat: asset.last_heartbeat,
      connectivity: asset.connectivity,
      health: asset.health,
    });
  }

  for (const asset of assets) {
    if (asset.asset_type === "node") {
      services.push({
        id: `${asset.fleet_id}-host-collector`,
        kind: "host-collector",
        name: "Host collector",
        subtitle: `${asset.fleet_id} · ${asset.hostname}`,
        version: asset.last_heartbeat?.collector_version ?? null,
        uptimeSeconds: null,
        heartbeat: asset.last_heartbeat,
        connectivity: asset.connectivity,
        health: asset.health,
      });
    } else if (asset.asset_type === "agent") {
      services.push({
        id: `${asset.fleet_id}-agent-collector`,
        kind: "agent-collector",
        name: "Agent collector",
        subtitle: `${asset.fleet_id} · ${asset.hostname}`,
        version: asset.last_heartbeat?.collector_version ?? null,
        uptimeSeconds: null,
        heartbeat: asset.last_heartbeat,
        connectivity: asset.connectivity,
        health: asset.health,
      });
    } else if (asset.asset_type === "service" && isExporter(asset)) {
      services.push({
        id: asset.fleet_id,
        kind: "exporter",
        name: asset.role || "Exporter",
        subtitle: `${asset.fleet_id} · ${asset.hostname}`,
        version: asset.software_version ?? asset.last_heartbeat?.software_version ?? null,
        uptimeSeconds: null,
        heartbeat: asset.last_heartbeat,
        connectivity: asset.connectivity,
        health: asset.health,
      });
    }
  }
  return services;
}
