/**
 * Events timeline tests (mission §6): rendering, filter-chip mapping,
 * severity derivation, empty/error states, and the documented
 * chip → event-type/severity contract in model.ts.
 */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "@/api/client";
import { makeEvent } from "@/test/fixtures";
import { renderRoute } from "@/test/utils";
import type { ObservatoryEvent } from "@/types";

import {
  eventDetail,
  eventKind,
  eventSeverity,
  eventTitle,
  filterEvents,
  sortEventsNewestFirst,
} from "./model";

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

const timelineFixture: ObservatoryEvent[] = [
  makeEvent({
    id: "e-1",
    event_type: "service_start",
    collector_id: "OBLN01",
    payload: { service: "observatory-backend", version: "0.3.1" },
  }),
  makeEvent({ id: "e-2", event_type: "heartbeat", collector_id: "RPSG01" }),
  makeEvent({
    id: "e-3",
    event_type: "asset_offline",
    collector_id: "observatory-backend",
    payload: { fleet_id: "A001" },
  }),
  makeEvent({
    id: "e-4",
    event_type: "docker_status",
    collector_id: "RPSG01",
    payload: {
      daemon_running: true,
      containers_total: 2,
      containers_running: 1,
      containers_failed: 1,
    },
  }),
];

beforeEach(() => {
  endpoints.listEvents.mockResolvedValue(timelineFixture);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("events timeline view", () => {
  it("renders the newest-first feed with titles, sources, and relative times", async () => {
    renderRoute("/events");

    expect(await screen.findByText("Service started")).toBeInTheDocument();
    const list = within(screen.getByRole("list", { name: "Event timeline" }));
    expect(list.getByText("Heartbeat")).toBeInTheDocument();
    expect(list.getByText("Asset went offline")).toBeInTheDocument();
    expect(list.getByText("Docker telemetry reported")).toBeInTheDocument();

    // Source asset and derived detail lines.
    expect(list.getByText("OBLN01")).toBeInTheDocument();
    expect(list.getByText(/1 of 2 containers running, 1 failed/)).toBeInTheDocument();
  });

  it("filters via chips and supports clearing back to All", async () => {
    const user = userEvent.setup();
    renderRoute("/events");
    await screen.findByText("Service started");

    const list = () => within(screen.getByRole("list", { name: "Event timeline" }));

    await user.click(screen.getByRole("button", { name: "Heartbeat", pressed: false }));
    expect(list().getByText("Heartbeat")).toBeInTheDocument();
    expect(list().queryByText("Service started")).not.toBeInTheDocument();

    // Chips combine as a union.
    await user.click(screen.getByRole("button", { name: "Error" }));
    expect(list().getByText("Asset went offline")).toBeInTheDocument();
    expect(list().queryByText("Service started")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "All" }));
    expect(list().getByText("Service started")).toBeInTheDocument();
  });

  it("labels warnings and errors with text, never colour alone", async () => {
    renderRoute("/events");
    await screen.findByText("Asset went offline");
    const list = within(screen.getByRole("list", { name: "Event timeline" }));
    expect(list.getByText("Error")).toBeInTheDocument(); // asset_offline
    expect(list.getByText("Warning")).toBeInTheDocument(); // docker failed container
  });

  it("shows a meaningful empty state for a filtered-out view", async () => {
    const user = userEvent.setup();
    endpoints.listEvents.mockResolvedValue([makeEvent({ id: "only", event_type: "heartbeat" })]);
    renderRoute("/events");
    await screen.findByRole("list", { name: "Event timeline" });

    await user.click(screen.getByRole("button", { name: "Error" }));
    expect(screen.getByText(/nothing matches these filters/i)).toBeInTheDocument();
  });

  it("shows a meaningful empty state for an empty stream", async () => {
    endpoints.listEvents.mockResolvedValue([]);
    renderRoute("/events");
    expect(await screen.findByText("No events yet")).toBeInTheDocument();
  });

  it("shows an error state with retry when the read fails", async () => {
    endpoints.listEvents.mockRejectedValue(
      new ApiRequestError({ kind: "network", detail: "Observatory backend unreachable." }),
    );
    renderRoute("/events");
    expect(await screen.findByText(/could not load data/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("event model (documented chip mapping)", () => {
  it("maps event types onto the mission's kind filters", () => {
    expect(eventKind(makeEvent({ event_type: "service_start" }))).toBe("service");
    expect(eventKind(makeEvent({ event_type: "mission_update" }))).toBe("service");
    expect(eventKind(makeEvent({ event_type: "system_metrics" }))).toBe("collector");
    expect(eventKind(makeEvent({ event_type: "docker_status" }))).toBe("collector");
    expect(eventKind(makeEvent({ event_type: "host_inventory" }))).toBe("collector");
    expect(eventKind(makeEvent({ event_type: "agent_status" }))).toBe("collector");
    expect(eventKind(makeEvent({ event_type: "heartbeat" }))).toBe("heartbeat");
    expect(eventKind(makeEvent({ event_type: "something_new" }))).toBe("other");
  });

  it("derives severity from type and payload signals", () => {
    expect(eventSeverity(makeEvent({ event_type: "asset_offline" }))).toBe("error");
    expect(eventSeverity(makeEvent({ event_type: "asset_online" }))).toBe("ok");
    expect(eventSeverity(makeEvent({ event_type: "heartbeat" }))).toBe("info");
    expect(
      eventSeverity(makeEvent({ event_type: "heartbeat", payload: { failures_total: 3 } })),
    ).toBe("warning");
    expect(
      eventSeverity(makeEvent({ event_type: "docker_status", payload: { daemon_running: false } })),
    ).toBe("warning");
    expect(
      eventSeverity(makeEvent({ event_type: "docker_status", payload: { containers_failed: 1 } })),
    ).toBe("warning");
    expect(
      eventSeverity(
        makeEvent({
          event_type: "docker_status",
          payload: { daemon_running: true, containers_failed: 0 },
        }),
      ),
    ).toBe("info");
  });

  it("presents events in source-time order, newest first", () => {
    const events = [
      makeEvent({
        id: "old",
        timestamp: "2026-07-22T04:00:00Z",
        received_at: "2026-07-22T06:00:00Z",
      }),
      makeEvent({
        id: "new",
        timestamp: "2026-07-22T05:00:00Z",
        received_at: "2026-07-22T05:00:01Z",
      }),
    ];
    // A late-arriving event (newer ingestion, older source time) still slots
    // into its true timeline position.
    expect(sortEventsNewestFirst(events).map((e) => e.id)).toEqual(["new", "old"]);
  });

  it("never drops unknown event types (schema-free stream)", () => {
    const unknown = makeEvent({ event_type: "brand_new_type" });
    expect(filterEvents([unknown], new Set())).toEqual([unknown]);
    expect(eventTitle(unknown)).toBe("brand_new_type");
    expect(eventDetail(unknown)).toBeNull();
  });

  it("derives short factual detail lines from well-known payloads", () => {
    expect(
      eventDetail(
        makeEvent({
          event_type: "system_metrics",
          payload: { cpu_percent: 12.34, memory: { used_percent: 55.5 } },
        }),
      ),
    ).toBe("CPU 12.3% · RAM 55.5%");
    expect(
      eventDetail(
        makeEvent({
          event_type: "mission_update",
          payload: { mission_id: "M004", state: "Running" },
        }),
      ),
    ).toBe("M004 → Running");
    expect(
      eventDetail(makeEvent({ event_type: "heartbeat", payload: { collector_version: "0.3.1" } })),
    ).toBe("collector 0.3.1");
  });
});
