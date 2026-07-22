import type { FleetAssetView, HealthResponse, HostInventoryRecord, MissionView } from "@/types";

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

/** Host Inventory shaped like the live RPSG01 payload (trimmed). */
export function makeInventory(overrides: Partial<HostInventoryRecord> = {}): HostInventoryRecord {
  return {
    fleet_id: "RPSG01",
    payload: {
      hardware: {
        manufacturer: "Raspberry Pi Foundation",
        model: "Raspberry Pi 4 Model B",
        revision: "c03114",
        cpu_model: "BCM2711",
        cpu_architecture: "ARM64",
        cpu_cores: 4,
        memory_total_bytes: 3_980_185_600,
        serial: "10000000bbc78bf0",
      },
      os: {
        name: "Debian GNU/Linux",
        release: "Trixie",
        version_id: "13",
        pretty_name: "Debian GNU/Linux 13 (trixie)",
        kernel: "6.18.34+rpt-rpi-v8",
        hostname: "raspberrypi-sg01",
      },
      storage: [
        {
          device: "/dev/mmcblk0p2",
          physical_device: "/dev/mmcblk0",
          type: "SD Card",
          transport: "SD",
          capacity_bytes: 62_192_091_136,
          mount: "/",
          brand: "SPCC",
          filesystem: "ext4",
          total_bytes: 60_605_497_344,
          used_bytes: 19_299_737_600,
          free_bytes: 41_305_759_744,
          used_percent: 31.84,
          name: "SD1",
        },
        {
          device: "/dev/mmcblk0p1",
          physical_device: "/dev/mmcblk0",
          type: "SD Card",
          transport: "SD",
          capacity_bytes: 62_192_091_136,
          mount: "/boot/firmware",
          brand: "SPCC",
          filesystem: "vfat",
          total_bytes: 528_592_896,
          used_bytes: 82_433_024,
          free_bytes: 446_159_872,
          used_percent: 15.59,
          name: "SD1",
        },
      ],
      network: {
        interfaces: [
          { name: "eth0", ipv4: "192.168.1.2", link_state: "up" },
          { name: "wlan0", ipv4: null, link_state: "down" },
        ],
        default_route: { gateway: "192.168.1.254", interface: "eth0" },
      },
      maintenance: {
        last_apt_update_epoch: 1_784_687_694,
        last_apt_upgrade: "2026-07-21 06:24:42",
        last_apt_full_upgrade: "2026-07-14 15:55:26",
        updates_available: 25,
        reboot_required: false,
      },
    },
    reported_at: "2026-07-22T06:58:28.679000Z",
    updated_at: "2026-07-22T06:58:28.700000Z",
    ...overrides,
  };
}

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
