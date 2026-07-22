/**
 * Mirrors backend/app/models/registry.py (Fleet Registry read models,
 * Mission M003 §1). Enums are string-literal unions matching the pydantic
 * StrEnum values exactly; timestamps arrive as ISO-8601 strings.
 */

export type AssetType = "agent" | "node" | "service" | "device" | "sensor";

export type DeploymentRole = "local" | "central";

export type LifecycleStatus =
  "Provisioned" | "Commissioning" | "Active" | "Paused" | "Suspended" | "Retired";

export type Environment = "Production" | "Staging" | "Development" | "Test";

export type Connectivity = "online" | "offline" | "unknown";

export type HealthStatus = "Healthy" | "Warning" | "Critical" | "Offline" | "Unknown";

/** Latest heartbeat details, derived from the event stream. */
export interface HeartbeatInfo {
  timestamp: string;
  received_at: string;
  software_version: string | null;
  collector_version: string | null;
  collector_type: string | null;
  schema_version: number | null;
}

/** Read model returned by GET /api/v1/fleet — identity + derived telemetry. */
export interface FleetAssetView {
  fleet_id: string;
  asset_type: AssetType;
  nickname: string | null;
  hostname: string;
  role: string;
  location: string;
  platform: string;
  os: string;
  software_version: string | null;
  host_fleet_id: string | null;
  deployment_role: DeploymentRole | null;
  service_version: string | null;
  capabilities: string[];
  tags: string[];
  status: LifecycleStatus;
  environment: Environment;
  registered_at: string;
  updated_at: string;
  last_heartbeat: HeartbeatInfo | null;
  connectivity: Connectivity;
  health: HealthStatus;
}
