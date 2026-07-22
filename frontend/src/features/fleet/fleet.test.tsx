/**
 * Fleet view tests (mission Testing & Quality): card rendering per health
 * state, hardware enrichment from Host Inventory, honest placeholders,
 * keyboard-navigable card links, empty and error states.
 */
import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "@/api/client";
import { fleetFixture, healthFixture, makeAsset, makeInventory } from "@/test/fixtures";
import { renderRoute } from "@/test/utils";

import { hardwareSummary } from "./hardware";

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
  endpoints.getHostInventory.mockResolvedValue(makeInventory());
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("fleet view", () => {
  it("renders one linked card per asset with the mission card fields", async () => {
    renderRoute("/fleet");

    const nodeCard = await screen.findByRole("link", {
      name: /raspberrypi-sg01 \(RPSG01\)/i,
    });
    expect(nodeCard).toHaveAttribute("href", "/fleet/RPSG01");
    expect(within(nodeCard).getByText("Singapore")).toBeInTheDocument();
    expect(within(nodeCard).getByText("Production")).toBeInTheDocument();
    expect(within(nodeCard).getByText("Raspberry Pi 5")).toBeInTheDocument();
    expect(within(nodeCard).getByText("Healthy")).toBeInTheDocument();
    expect(within(nodeCard).getByText(/ago$/)).toBeInTheDocument(); // heartbeat
    expect(within(nodeCard).getByText("0.3.1")).toBeInTheDocument(); // collector version
    // Hardware comes from the Host Inventory endpoint (nodes only).
    expect(await within(nodeCard).findByText("Raspberry Pi 4 Model B · 4 GB")).toBeInTheDocument();
    // Uptime is not exposed by the REST API — honest placeholder, never a fake value.
    expect(within(nodeCard).getAllByText("Not reported").length).toBeGreaterThan(0);

    // One card per fixture asset (node, service, agent).
    expect(screen.getAllByRole("link", { name: /details$/i })).toHaveLength(3);
  });

  it("communicates every health state as a text label, never colour alone", async () => {
    endpoints.listFleet.mockResolvedValue([
      makeAsset({ fleet_id: "N1", hostname: "n1", health: "Healthy" }),
      makeAsset({ fleet_id: "N2", hostname: "n2", health: "Warning" }),
      makeAsset({ fleet_id: "N3", hostname: "n3", health: "Critical" }),
      makeAsset({ fleet_id: "N4", hostname: "n4", health: "Offline", connectivity: "offline" }),
      makeAsset({ fleet_id: "N5", hostname: "n5", health: "Unknown", last_heartbeat: null }),
    ]);
    renderRoute("/fleet");

    for (const label of ["Healthy", "Warning", "Critical", "Offline", "Unknown"]) {
      expect(await screen.findByText(label)).toBeInTheDocument();
    }
    // A heartbeat-less asset says "Never", not a blank.
    expect(screen.getByText("Never")).toBeInTheDocument();
  });

  it("shows a meaningful empty state when the registry is empty", async () => {
    endpoints.listFleet.mockResolvedValue([]);
    renderRoute("/fleet");
    expect(await screen.findByText("No assets registered")).toBeInTheDocument();
  });

  it("points at Settings on an auth failure", async () => {
    endpoints.listFleet.mockRejectedValue(
      new ApiRequestError({ kind: "http", status: 401, detail: "Invalid API key." }),
    );
    renderRoute("/fleet");
    expect(await screen.findByText(/rejected the api key/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Settings" })).toBeInTheDocument();
  });

  it("shows a retryable error state when the backend is unreachable", async () => {
    endpoints.listFleet.mockRejectedValue(
      new ApiRequestError({ kind: "network", detail: "Observatory backend unreachable." }),
    );
    renderRoute("/fleet");
    expect(await screen.findByText(/could not load data/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("keeps hardware as a placeholder when a node has no inventory", async () => {
    endpoints.getHostInventory.mockRejectedValue(
      new ApiRequestError({
        kind: "http",
        status: 404,
        detail: "No host inventory reported for this fleet_id yet.",
      }),
    );
    renderRoute("/fleet");
    const nodeCard = await screen.findByRole("link", { name: /raspberrypi-sg01 \(RPSG01\)/i });
    // Hardware and Uptime rows both fall back to the honest placeholder.
    expect(within(nodeCard).getAllByText("Not reported").length).toBeGreaterThanOrEqual(2);
  });
});

describe("hardwareSummary", () => {
  it("joins model and marketed memory size", () => {
    expect(hardwareSummary(makeInventory())).toBe("Raspberry Pi 4 Model B · 4 GB");
  });

  it("returns null when the hardware section is missing", () => {
    expect(hardwareSummary(makeInventory({ payload: {} }))).toBeNull();
    expect(hardwareSummary(undefined)).toBeNull();
  });

  it("copes with a partial hardware section", () => {
    expect(
      hardwareSummary(makeInventory({ payload: { hardware: { model: "Generic Box" } } })),
    ).toBe("Generic Box");
  });
});
