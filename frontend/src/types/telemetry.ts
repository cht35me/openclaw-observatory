/**
 * Mirrors backend/app/models/telemetry.py (M004 PR3, additive): the newest
 * stored telemetry event of one allowlisted type for one fleet asset —
 * today exactly `docker_status` via GET /api/v1/fleet/{id}/docker-status.
 *
 * The payload is schema-flexible on the wire (collectors fail soft), so
 * every payload field below is optional and consumers render "Not reported"
 * when a value is absent — never a fake zero.
 */

/** Per-container facts + stats from the host collector's docker_status payload. */
export interface DockerContainer {
  name?: string;
  image?: string | null;
  status?: string | null;
  exit_code?: number | null;
  restart_count?: number | null;
  started_at?: string | null;
  uptime_seconds?: number | null;
  network_mode?: string | null;
  networks?: string[];
  cpu_percent?: number | null;
  memory_percent?: number | null;
  /** e.g. "132MiB / 3.7GiB" — docker stats' own rendering, shown verbatim. */
  memory_usage?: string | null;
  network_rx_bytes?: number | null;
  network_tx_bytes?: number | null;
}

/** docker_status event payload (collectors/host_pi/docker_stats.py). */
export interface DockerStatusPayload {
  daemon_running?: boolean;
  containers_total?: number;
  containers_running?: number;
  containers_failed?: number;
  restart_count_total?: number;
  containers?: DockerContainer[];
}

/** GET /api/v1/fleet/{id}/docker-status response. */
export interface TelemetrySnapshot<P = DockerStatusPayload> {
  fleet_id: string;
  event_type: string;
  /** Source timestamp (collector clock, UTC). */
  timestamp: string;
  /** Ingestion timestamp stamped by the backend. */
  received_at: string;
  schema_version: number;
  payload: P;
}
