/**
 * Dashboard critical rendering tests (mission Testing & Quality) with the
 * endpoint layer mocked: happy path, auth-error path, and empty states.
 */
import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "@/api/client";
import { fleetFixture, healthFixture, makeMission } from "@/test/fixtures";
import { renderRoute } from "@/test/utils";

import {
  selectActiveMission,
  selectObservatoryEnvironment,
  summarizeFleet,
} from "./useDashboardData";

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
  endpoints.listMissions.mockResolvedValue([
    makeMission({ mission_id: "M003", state: "Completed", updated_at: "2026-07-21T00:00:00Z" }),
    makeMission(),
  ]);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("dashboard rendering", () => {
  it("renders observatory, mission, and fleet cards from live data", async () => {
    renderRoute("/");

    // Observatory card (/health + environment from the registry).
    expect(await screen.findByText("Operational")).toBeInTheDocument();
    expect(screen.getByText("v0.3.1")).toBeInTheDocument();
    expect(screen.getByText("1d 2h")).toBeInTheDocument();
    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("Production")).toBeInTheDocument();

    // Active mission card: newest non-completed mission wins.
    expect(await screen.findByText("M004")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText("Observatory Visibility & Frontend")).toBeInTheDocument();

    // Fleet summary card: 3 assets, 1 node / 1 service / 1 agent, 2 online.
    expect(await screen.findByText("1 / 1 / 1")).toBeInTheDocument();
    expect(screen.getByText("2 of 3")).toBeInTheDocument();
    expect(screen.getByText("2 Healthy")).toBeInTheDocument();
    expect(screen.getByText("1 Unknown")).toBeInTheDocument();
  });

  it("points at Settings when the fleet read is rejected as unauthorized", async () => {
    endpoints.listFleet.mockRejectedValue(
      new ApiRequestError({ kind: "http", status: 401, detail: "Invalid API key." }),
    );
    renderRoute("/");

    expect(await screen.findByText(/rejected the api key/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Settings" })).toHaveAttribute(
      "href",
      "/settings",
    );
  });

  it("shows a meaningful empty state when no mission is in flight", async () => {
    endpoints.listMissions.mockResolvedValue([
      makeMission({ mission_id: "M003", state: "Completed" }),
    ]);
    renderRoute("/");

    expect(await screen.findByText(/no mission in flight/i)).toBeInTheDocument();
  });

  it("shows a retryable error card when the backend is unreachable", async () => {
    endpoints.listMissions.mockRejectedValue(
      new ApiRequestError({ kind: "network", detail: "Observatory backend unreachable." }),
    );
    renderRoute("/");

    expect(await screen.findByText(/could not load data/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("dashboard selectors", () => {
  it("selectActiveMission prefers the newest non-completed mission", () => {
    const missions = [
      makeMission({ mission_id: "M002", state: "Review", updated_at: "2026-07-01T00:00:00Z" }),
      makeMission({ mission_id: "M004", state: "Running", updated_at: "2026-07-22T00:00:00Z" }),
      makeMission({ mission_id: "M003", state: "Completed", updated_at: "2026-07-23T00:00:00Z" }),
    ];
    expect(selectActiveMission(missions)?.mission_id).toBe("M004");
    expect(selectActiveMission([])).toBeNull();
  });

  it("summarizeFleet counts types, connectivity, and health", () => {
    const summary = summarizeFleet(fleetFixture);
    expect(summary.total).toBe(3);
    expect(summary.byType).toEqual({ nodes: 1, services: 1, agents: 1, other: 0 });
    expect(summary.connectivity).toEqual({ online: 2, offline: 0, unknown: 1 });
    expect(summary.health.Healthy).toBe(2);
    expect(summary.health.Unknown).toBe(1);
  });

  it("selectObservatoryEnvironment reads the observatory service asset", () => {
    expect(selectObservatoryEnvironment(fleetFixture)).toBe("Production");
    expect(selectObservatoryEnvironment([])).toBeNull();
  });
});
