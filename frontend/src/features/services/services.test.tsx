/**
 * Services view tests (mission Testing & Quality): derived service groups,
 * real values where the REST API provides them, honest "Not reported"
 * fallbacks where it does not, and error/empty states.
 */
import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "@/api/client";
import { fleetFixture, healthFixture, makeAsset } from "@/test/fixtures";
import { renderRoute } from "@/test/utils";

import { deriveServices } from "./useServicesData";

vi.mock("@/api/endpoints", () => ({
  getHealth: vi.fn(),
  listFleet: vi.fn(),
  listMissions: vi.fn(),
  getFleetAsset: vi.fn(),
  getHostInventory: vi.fn(),
  probeAuthenticated: vi.fn(),
}));

const endpoints = vi.mocked(await import("@/api/endpoints"));

beforeEach(() => {
  endpoints.getHealth.mockResolvedValue(healthFixture);
  endpoints.listFleet.mockResolvedValue(fleetFixture);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("services view", () => {
  it("groups backend, host collector, and agent collector with live values", async () => {
    renderRoute("/services");

    // Groups (mission §5) render as labelled sections.
    for (const heading of ["Backend", "Host collectors", "Agent collectors", "Exporters"]) {
      expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
    }

    // Backend card: version from the registry, uptime from /health.
    const backend = screen
      .getByRole("heading", { name: "Backend" })
      .closest("section") as HTMLElement;
    expect(within(backend).getByText("OBLN01 · raspberrypi-sg01")).toBeInTheDocument();
    expect(within(backend).getByText("1d 2h")).toBeInTheDocument(); // 93 784 s

    // Host collector card: collector version from the last heartbeat.
    const hosts = screen
      .getByRole("heading", { name: "Host collectors" })
      .closest("section") as HTMLElement;
    expect(within(hosts).getByText("Host collector")).toBeInTheDocument();
    expect(within(hosts).getByText("0.3.1")).toBeInTheDocument();
    expect(within(hosts).getByText(/ago$/)).toBeInTheDocument();

    // Agent collector without a heartbeat says "Never" and stays honest.
    const agents = screen
      .getByRole("heading", { name: "Agent collectors" })
      .closest("section") as HTMLElement;
    expect(within(agents).getByText("Never")).toBeInTheDocument();

    // No exporters are registered — meaningful empty text, not a blank.
    expect(screen.getByText(/no exporters registered/i)).toBeInTheDocument();

    // Restart count / CPU / RAM / RX / TX are not exposed over REST today.
    expect(screen.getAllByText("Not reported").length).toBeGreaterThanOrEqual(15);
    expect(screen.getByRole("note")).toHaveTextContent(/not expose them yet/i);
  });

  it("still renders collectors when /health is unavailable (backend uptime degrades honestly)", async () => {
    endpoints.getHealth.mockRejectedValue(
      new ApiRequestError({ kind: "network", detail: "Observatory backend unreachable." }),
    );
    renderRoute("/services");

    const backend = (await screen.findByRole("heading", { name: "Backend" })).closest(
      "section",
    ) as HTMLElement;
    expect(within(backend).getByText("OBLN01 · raspberrypi-sg01")).toBeInTheDocument();
    expect(within(backend).queryByText("1d 2h")).not.toBeInTheDocument();
  });

  it("shows an error state when the fleet read fails", async () => {
    endpoints.listFleet.mockRejectedValue(
      new ApiRequestError({ kind: "network", detail: "Observatory backend unreachable." }),
    );
    renderRoute("/services");
    expect(await screen.findByText(/could not load data/i)).toBeInTheDocument();
  });

  it("shows a meaningful empty state for an empty registry", async () => {
    endpoints.listFleet.mockResolvedValue([]);
    renderRoute("/services");
    expect(await screen.findByText("No services registered")).toBeInTheDocument();
  });
});

describe("deriveServices", () => {
  it("classifies exporter service assets by role/tags", () => {
    const assets = [
      makeAsset({ fleet_id: "EXP01", asset_type: "service", role: "Node Exporter" }),
      makeAsset({ fleet_id: "OBLN01", asset_type: "service", role: "Observatory Backend" }),
    ];
    const services = deriveServices(assets, healthFixture);
    expect(services.find((s) => s.id === "EXP01")?.kind).toBe("exporter");
    expect(services.find((s) => s.id === "OBLN01")?.kind).toBe("backend");
  });

  it("attaches /health uptime only when exactly one backend exists", () => {
    const one = deriveServices(
      [makeAsset({ fleet_id: "OBLN01", asset_type: "service", role: "Backend" })],
      healthFixture,
    );
    expect(one[0]?.uptimeSeconds).toBe(healthFixture.uptime_seconds);

    const two = deriveServices(
      [
        makeAsset({ fleet_id: "OBLN01", asset_type: "service", role: "Backend" }),
        makeAsset({ fleet_id: "OBC01", asset_type: "service", role: "Central Backend" }),
      ],
      healthFixture,
    );
    expect(two.every((s) => s.uptimeSeconds === null)).toBe(true);
  });

  it("never invents uptime for collectors", () => {
    const services = deriveServices(fleetFixture, healthFixture);
    for (const service of services) {
      if (service.kind !== "backend") expect(service.uptimeSeconds).toBeNull();
    }
  });
});
