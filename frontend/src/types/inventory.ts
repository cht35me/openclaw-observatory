/**
 * Mirrors backend/app/models/inventory.py (Host Inventory, Mission M003.5 §3).
 *
 * The backend stores the payload as a validated-but-open dict — sections are
 * collector-versioned and may gain keys without a backend schema change. The
 * mirror therefore types every section and field as optional/nullable: the
 * UI must render gracefully when a section is missing or partial.
 */

/** hardware section — manufacturer/model/CPU/memory identity (§3a). */
export interface HardwareInventory {
  manufacturer?: string | null;
  model?: string | null;
  revision?: string | null;
  cpu_model?: string | null;
  cpu_architecture?: string | null;
  cpu_cores?: number | null;
  memory_total_bytes?: number | null;
  serial?: string | null;
}

/** os section — /etc/os-release identity + kernel + hostname (§3c). */
export interface OsInventory {
  name?: string | null;
  release?: string | null;
  version_id?: string | null;
  pretty_name?: string | null;
  kernel?: string | null;
  hostname?: string | null;
}

/**
 * One entry per mounted, block-device-backed filesystem (§3b). Extra keys
 * (e.g. future SMART attributes) are preserved by the backend verbatim.
 */
export interface StorageDevice {
  name?: string | null;
  device?: string | null;
  physical_device?: string | null;
  type?: string | null;
  transport?: string | null;
  capacity_bytes?: number | null;
  mount?: string | null;
  brand?: string | null;
  filesystem?: string | null;
  total_bytes?: number | null;
  used_bytes?: number | null;
  free_bytes?: number | null;
  used_percent?: number | null;
}

export interface NetworkInterface {
  name?: string | null;
  ipv4?: string | null;
  link_state?: string | null;
}

export interface DefaultRoute {
  gateway?: string | null;
  interface?: string | null;
}

export interface NetworkInventory {
  interfaces?: NetworkInterface[] | null;
  default_route?: DefaultRoute | null;
}

/** maintenance section — apt/reboot status (§3d). */
export interface MaintenanceInventory {
  last_apt_update_epoch?: number | null;
  last_apt_upgrade?: string | null;
  last_apt_full_upgrade?: string | null;
  updates_available?: number | null;
  reboot_required?: boolean | null;
}

/** The schema-flexible payload; every section is optional (fail-soft collector). */
export interface HostInventoryPayload {
  hardware?: HardwareInventory | null;
  os?: OsInventory | null;
  storage?: StorageDevice[] | null;
  network?: NetworkInventory | null;
  maintenance?: MaintenanceInventory | null;
}

/** Read model of GET /api/v1/fleet/{fleetId}/inventory (404 when never reported). */
export interface HostInventoryRecord {
  fleet_id: string;
  payload: HostInventoryPayload;
  reported_at: string;
  updated_at: string;
}
