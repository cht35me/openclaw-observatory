/**
 * Services runtime view model (mission §5), derived from the REST reads that
 * exist after M004 PR3: GET /api/v1/fleet (identity, heartbeat with
 * uptime/failures, health), GET /health (backend uptime), and
 * GET /api/v1/fleet/{id}/docker-status (per-container restart count, CPU,
 * RAM, RX/TX for containerized services).
 *
 * Honesty over decoration: services that run as plain systemd processes
 * (the collectors, and the backend today) have no per-process telemetry —
 * those fields render "Not reported", never a fake zero.
 */
import { useQueries } from "@tanstack/react-query";

import { getDockerStatus } from "@/api/endpoints";
import { POLL_INTERVALS } from "@/api/queryClient";
import { queryKeys } from "@/api/queryKeys";
import type {
  Connectivity,
  DockerContainer,
  DockerStatusPayload,
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
  /** Backend: /health uptime. Collectors: heartbeat uptime_seconds (PR3). */
  uptimeSeconds: number | null;
  /** Cumulative collector failures from the heartbeat (PR3), null when unreported. */
  failuresTotal: number | null;
  heartbeat: HeartbeatInfo | null;
  connectivity: Connectivity;
  health: HealthStatus;
  /** Matching container from the host's docker_status telemetry, if any. */
  container: DockerContainer | null;
  /** Whether the service's host reported Docker telemetry at all. */
  dockerReported: boolean;
}

function isExporter(asset: FleetAssetView): boolean {
  const haystack = `${asset.role} ${asset.tags.join(" ")}`.toLowerCase();
  return haystack.includes("exporter");
}

/** Lowercase slug for name matching: "Observatory Backend" → "observatory-backend". */
function slugify(value: string | null | undefined): string | null {
  if (!value) return null;
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug.length > 0 ? slug : null;
}

/**
 * Match a service asset to a container in its host's Docker telemetry.
 *
 * Deliberately strict (documented heuristic): the container name must
 * *equal* the slug of the service's fleet id, nickname, or role (e.g. role
 * "Bitaxe Exporter" ↔ container "bitaxe-exporter"). Near-misses stay
 * unmatched and render "Not reported"; a wrong match would show another
 * workload's numbers, which is worse than a gap.
 */
export function matchContainer(
  asset: FleetAssetView,
  containers: DockerContainer[] | undefined,
): DockerContainer | null {
  if (!containers || containers.length === 0) return null;
  const candidates = [asset.fleet_id, asset.nickname, asset.role]
    .map(slugify)
    .filter((slug): slug is string => slug !== null && slug.length >= 4);
  for (const container of containers) {
    const name = slugify(container.name);
    if (!name) continue;
    if (candidates.some((candidate) => name === candidate)) {
      return container;
    }
  }
  return null;
}

/**
 * Latest docker_status telemetry for every *node* in the fleet, keyed by
 * fleet id. 404 means "no docker telemetry reported" — a normal condition
 * (isNotFoundError), cached as absence rather than retried.
 */
export function useDockerStatuses(
  assets: FleetAssetView[] | undefined,
): Map<string, DockerStatusPayload> {
  const nodes = (assets ?? []).filter((asset) => asset.asset_type === "node");
  const results = useQueries({
    queries: nodes.map((node) => ({
      queryKey: queryKeys.dockerStatus(node.fleet_id),
      queryFn: ({ signal }: { signal: AbortSignal }) => getDockerStatus(node.fleet_id, signal),
      refetchInterval: POLL_INTERVALS.dockerStatus,
    })),
  });
  const byFleetId = new Map<string, DockerStatusPayload>();
  results.forEach((result, index) => {
    const node = nodes[index];
    if (node && result.data) byFleetId.set(node.fleet_id, result.data.payload);
  });
  return byFleetId;
}

function collectorRuntime(
  asset: FleetAssetView,
  kind: "host-collector" | "agent-collector",
): ServiceRuntime {
  return {
    id: `${asset.fleet_id}-${kind}`,
    kind,
    name: kind === "host-collector" ? "Host collector" : "Agent collector",
    subtitle: `${asset.fleet_id} · ${asset.hostname}`,
    version: asset.last_heartbeat?.collector_version ?? null,
    uptimeSeconds: asset.last_heartbeat?.uptime_seconds ?? null,
    failuresTotal: asset.last_heartbeat?.failures_total ?? null,
    heartbeat: asset.last_heartbeat,
    connectivity: asset.connectivity,
    health: asset.health,
    container: null, // collectors run as systemd processes, not containers
    dockerReported: false,
  };
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
  dockerByHost: Map<string, DockerStatusPayload> = new Map(),
): ServiceRuntime[] {
  const services: ServiceRuntime[] = [];
  const backends = assets.filter((a) => a.asset_type === "service" && !isExporter(a));

  const dockerFor = (asset: FleetAssetView) => {
    const hostId = asset.host_fleet_id ?? asset.fleet_id;
    const docker = dockerByHost.get(hostId);
    return {
      container: docker ? matchContainer(asset, docker.containers) : null,
      dockerReported: docker !== undefined,
    };
  };

  for (const asset of backends) {
    services.push({
      id: asset.fleet_id,
      kind: "backend",
      name: asset.role || "Backend",
      subtitle: `${asset.fleet_id} · ${asset.hostname}`,
      version: asset.software_version ?? asset.last_heartbeat?.software_version ?? null,
      uptimeSeconds:
        backends.length === 1 && health
          ? health.uptime_seconds
          : (asset.last_heartbeat?.uptime_seconds ?? null),
      failuresTotal: asset.last_heartbeat?.failures_total ?? null,
      heartbeat: asset.last_heartbeat,
      connectivity: asset.connectivity,
      health: asset.health,
      ...dockerFor(asset),
    });
  }

  for (const asset of assets) {
    if (asset.asset_type === "node") {
      services.push(collectorRuntime(asset, "host-collector"));
    } else if (asset.asset_type === "agent") {
      services.push(collectorRuntime(asset, "agent-collector"));
    } else if (asset.asset_type === "service" && isExporter(asset)) {
      services.push({
        id: asset.fleet_id,
        kind: "exporter",
        name: asset.role || "Exporter",
        subtitle: `${asset.fleet_id} · ${asset.hostname}`,
        version: asset.software_version ?? asset.last_heartbeat?.software_version ?? null,
        uptimeSeconds: asset.last_heartbeat?.uptime_seconds ?? null,
        failuresTotal: asset.last_heartbeat?.failures_total ?? null,
        heartbeat: asset.last_heartbeat,
        connectivity: asset.connectivity,
        health: asset.health,
        ...dockerFor(asset),
      });
    }
  }
  return services;
}
