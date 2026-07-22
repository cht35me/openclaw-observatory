/**
 * Services view tests (mission Testing & Quality): derived service groups,
 * real values where the REST API provides them, honest "Not reported"
 * fallbacks where it does not, and error/empty states.
 */
import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "@/api/client";
import { fleetFixture, healthFixture, makeAsset, makeDockerStatus } from "@/test/fixtures";
import { renderRoute } from "@/test/utils";

import { deriveServices, matchContainer } from "./useServicesData";

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

beforeEach(() => {
  endpoints.getHealth.mockResolvedValue(healthFixture);
  endpoints.listFleet.mockResolvedValue(fleetFixture);
  endpoints.getDockerStatus.mockResolvedValue(makeDockerStatus());
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

    // No fixture service maps to a container, so container stats stay honest.
    expect(screen.getAllByText("Not reported").length).toBeGreaterThanOrEqual(10);
    expect(screen.getByRole("note")).toHaveTextContent(/containerized services only/i);
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
    // PR3: without /health, uptime falls back to the backend's own
    // self-heartbeat (which carries uptime_seconds) — still a fact, not a guess.
    expect(within(backend).getByText("1d 2h")).toBeInTheDocument();
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

  it("prefers /health uptime for a single backend, heartbeat uptime otherwise", () => {
    const one = deriveServices(
      [makeAsset({ fleet_id: "OBLN01", asset_type: "service", role: "Backend" })],
      healthFixture,
    );
    expect(one[0]?.uptimeSeconds).toBe(healthFixture.uptime_seconds);

    // With two backends, /health cannot be attributed — each falls back to
    // its own heartbeat's uptime_seconds (PR3 additive field).
    const two = deriveServices(
      [
        makeAsset({ fleet_id: "OBLN01", asset_type: "service", role: "Backend" }),
        makeAsset({ fleet_id: "OBC01", asset_type: "service", role: "Central Backend" }),
      ],
      healthFixture,
    );
    expect(two.every((s) => s.uptimeSeconds === 93_784)).toBe(true);
  });

  it("collector uptime comes from its heartbeat and is never invented", () => {
    const services = deriveServices(fleetFixture, healthFixture);
    const host = services.find((s) => s.kind === "host-collector");
    const agent = services.find((s) => s.kind === "agent-collector");
    expect(host?.uptimeSeconds).toBe(93_784); // fixture heartbeat uptime_seconds
    expect(host?.failuresTotal).toBe(0);
    expect(agent?.uptimeSeconds).toBeNull(); // no heartbeat → null, never fabricated
    expect(agent?.failuresTotal).toBeNull();
  });

  it("maps docker container stats onto matching services only", () => {
    const docker = makeDockerStatus().payload;
    const byHost = new Map([["RPSG01", docker]]);
    const exporter = makeAsset({
      fleet_id: "BXE01",
      asset_type: "service",
      nickname: "Bitaxe Exporter",
      role: "bitaxe-exporter",
      host_fleet_id: "RPSG01",
      deployment_role: "local",
    });
    const backend = makeAsset({
      fleet_id: "OBLN01",
      asset_type: "service",
      role: "Observatory Backend",
      host_fleet_id: "RPSG01",
      deployment_role: "local",
    });
    const services = deriveServices([exporter, backend], healthFixture, byHost);

    const matched = services.find((s) => s.id === "BXE01");
    expect(matched?.container?.name).toBe("bitaxe-exporter");
    expect(matched?.container?.cpu_percent).toBe(0.42);
    expect(matched?.dockerReported).toBe(true);

    // The backend runs as a systemd process — no container match, no fake stats.
    const unmatched = services.find((s) => s.id === "OBLN01");
    expect(unmatched?.container).toBeNull();
    expect(unmatched?.dockerReported).toBe(true);
  });
});

describe("matchContainer", () => {
  const containers = makeDockerStatus().payload.containers;

  it("matches on the exact slug of fleet id, nickname, or role", () => {
    expect(
      matchContainer(makeAsset({ nickname: null, role: "Bitaxe Exporter" }), containers)?.name,
    ).toBe("bitaxe-exporter");
  });

  it("stays unmatched rather than guessing", () => {
    expect(
      matchContainer(makeAsset({ nickname: null, role: "Observatory Backend" }), containers),
    ).toBeNull();
    // Partial overlap is not a match — a generic role must never claim
    // another workload's container stats.
    expect(matchContainer(makeAsset({ nickname: null, role: "exporter" }), containers)).toBeNull();
  });
});
