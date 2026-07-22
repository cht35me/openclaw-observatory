/**
 * Node details tests (mission Testing & Quality): full Host Inventory
 * rendering, partial-inventory grace, the no-inventory (404) path for
 * agents/services, and the unknown-asset path.
 */
import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "@/api/client";
import {
  fleetFixture,
  healthFixture,
  makeAsset,
  makeDockerStatus,
  makeInventory,
} from "@/test/fixtures";
import { renderRoute } from "@/test/utils";

vi.mock("@/api/endpoints", () => ({
  getHealth: vi.fn(),
  listFleet: vi.fn(),
  listMissions: vi.fn(),
  getFleetAsset: vi.fn(),
  getHostInventory: vi.fn(),
  getDockerStatus: vi.fn(),
  listEvents: vi.fn(),
  probeAuthenticated: vi.fn(),
}));

const endpoints = vi.mocked(await import("@/api/endpoints"));

const notFound = (detail: string) => new ApiRequestError({ kind: "http", status: 404, detail });

beforeEach(() => {
  endpoints.getHealth.mockResolvedValue(healthFixture);
  endpoints.getFleetAsset.mockResolvedValue(fleetFixture[0]!);
  endpoints.getHostInventory.mockResolvedValue(makeInventory());
  endpoints.getDockerStatus.mockResolvedValue(makeDockerStatus());
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("node details", () => {
  it("renders identity plus every Host Inventory section", async () => {
    renderRoute("/fleet/RPSG01");

    // Header: hostname + health + connectivity as text labels.
    expect(await screen.findByRole("heading", { name: "raspberrypi-sg01" })).toBeInTheDocument();
    expect(screen.getByText("Healthy")).toBeInTheDocument();
    expect(screen.getByText("Online")).toBeInTheDocument();
    expect(screen.getByText(/inventory reported/i)).toBeInTheDocument();

    // All mission §4 sections are present.
    for (const section of [
      "Identity",
      "Hardware",
      "Operating System",
      "Storage",
      "Interfaces",
      "Maintenance",
      "Running Services",
      "Docker Containers",
    ]) {
      expect(screen.getByRole("heading", { name: section })).toBeInTheDocument();
    }

    // Hardware facts.
    expect(screen.getByText("Raspberry Pi 4 Model B (rev c03114)")).toBeInTheDocument();
    expect(screen.getByText("BCM2711 · ARM64 · 4 cores")).toBeInTheDocument();
    expect(screen.getByText("4 GB")).toBeInTheDocument();
    expect(screen.getByText("10000000bbc78bf0")).toBeInTheDocument();

    // OS facts.
    expect(screen.getByText("Debian GNU/Linux 13 (trixie)")).toBeInTheDocument();
    expect(screen.getByText("6.18.34+rpt-rpi-v8")).toBeInTheDocument();

    // Storage: two mounts of the same SD card.
    expect(screen.getAllByText("SD1")).toHaveLength(2);
    expect(screen.getByText("/boot/firmware")).toBeInTheDocument();
    expect(screen.getByText(/31\.8%/)).toBeInTheDocument();

    // Interfaces with link state as text.
    expect(screen.getByText("eth0")).toBeInTheDocument();
    expect(screen.getByText("192.168.1.2")).toBeInTheDocument();
    expect(screen.getByText("UP")).toBeInTheDocument();
    expect(screen.getByText("DOWN")).toBeInTheDocument();
    expect(screen.getByText(/default route: 192\.168\.1\.254 via eth0/i)).toBeInTheDocument();

    // Maintenance.
    expect(screen.getByText("25")).toBeInTheDocument();
    expect(screen.getByText("No")).toBeInTheDocument();
    expect(screen.getByText("2026-07-14 15:55:26")).toBeInTheDocument();

    // Running Services stays an honest placeholder (no collector source yet).
    expect(screen.getByText(/does not observe systemd services yet/i)).toBeInTheDocument();

    // Docker Containers renders live telemetry (M004 PR3 docker-status route).
    expect(await screen.findByText("1 of 1 running")).toBeInTheDocument();
    expect(screen.getByText("bitaxe-exporter")).toBeInTheDocument();
    expect(screen.getByText("68MiB / 3.7GiB")).toBeInTheDocument();
  });

  it("renders Docker Containers as not reported on the route's 404", async () => {
    endpoints.getDockerStatus.mockRejectedValue(
      notFound("No docker telemetry reported for this fleet_id yet."),
    );
    renderRoute("/fleet/RPSG01");
    expect(await screen.findByText(/docker telemetry not reported/i)).toBeInTheDocument();
  });

  it("shows a stopped Docker daemon as a labelled critical state", async () => {
    endpoints.getDockerStatus.mockResolvedValue(
      makeDockerStatus({ payload: { daemon_running: false } }),
    );
    renderRoute("/fleet/RPSG01");
    expect(await screen.findByText(/docker daemon not running/i)).toBeInTheDocument();
  });

  it("renders gracefully when inventory sections are missing (partial payload)", async () => {
    endpoints.getHostInventory.mockResolvedValue(
      makeInventory({
        payload: { os: { name: "Debian GNU/Linux", kernel: "6.18.34" } },
      }),
    );
    renderRoute("/fleet/RPSG01");

    expect(await screen.findByText("Debian GNU/Linux")).toBeInTheDocument();
    expect(screen.getByText(/hardware identity not reported/i)).toBeInTheDocument();
    expect(screen.getByText(/storage inventory not reported/i)).toBeInTheDocument();
    expect(screen.getByText(/network interfaces not reported/i)).toBeInTheDocument();
    expect(screen.getByText(/maintenance status not reported/i)).toBeInTheDocument();
  });

  it("explains missing inventory for a non-node asset and links to its host", async () => {
    endpoints.getFleetAsset.mockResolvedValue(
      makeAsset({
        fleet_id: "A001",
        asset_type: "agent",
        hostname: "raspberrypi-sg01",
        host_fleet_id: "RPSG01",
      }),
    );
    endpoints.getHostInventory.mockRejectedValue(
      notFound("No host inventory reported for this fleet_id yet."),
    );
    renderRoute("/fleet/A001");

    expect(await screen.findByText("No host inventory")).toBeInTheDocument();
    expect(screen.getByText(/this asset is a agent/i)).toBeInTheDocument();
    const hostLink = screen.getByRole("link", { name: /view host RPSG01/i });
    expect(hostLink).toHaveAttribute("href", "/fleet/RPSG01");
    // Inventory sections are not faked for assets that never report them.
    expect(screen.queryByRole("heading", { name: "Hardware" })).not.toBeInTheDocument();
  });

  it("tells a node apart: inventory simply not received yet", async () => {
    endpoints.getHostInventory.mockRejectedValue(
      notFound("No host inventory reported for this fleet_id yet."),
    );
    renderRoute("/fleet/RPSG01");

    expect(await screen.findByText("No host inventory")).toBeInTheDocument();
    expect(screen.getByText(/has not reported a host_inventory event yet/i)).toBeInTheDocument();
  });

  it("shows an unknown-asset state with a way back for a 404 fleet id", async () => {
    endpoints.getFleetAsset.mockRejectedValue(notFound("Unknown fleet_id."));
    endpoints.getHostInventory.mockRejectedValue(notFound("Unknown fleet_id."));
    renderRoute("/fleet/NOPE");

    expect(await screen.findByText("Unknown fleet asset")).toBeInTheDocument();
    const back = screen.getByRole("link", { name: /back to fleet/i });
    expect(back).toHaveAttribute("href", "/fleet");
  });

  it("shows a retryable error state when the inventory read fails hard", async () => {
    endpoints.getHostInventory.mockRejectedValue(
      new ApiRequestError({ kind: "http", status: 503, detail: "Storage backend unavailable." }),
    );
    renderRoute("/fleet/RPSG01");

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(/could not load data/i)).toBeInTheDocument();
    expect(within(alert).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    // Registry identity still renders around the failing section.
    expect(screen.getByRole("heading", { name: "Identity" })).toBeInTheDocument();
  });
});
