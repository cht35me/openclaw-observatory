/**
 * Events timeline domain model (mission §6): map raw telemetry events onto
 * presentation categories, severities, and human titles.
 *
 * ## Filter-chip mapping (documented contract)
 *
 * The mission names five filters — service, collector, heartbeat, warning,
 * error. The first three are *kind* filters (what emitted the event), the
 * last two are *severity* filters (how much attention it needs):
 *
 * | Chip      | Matches                                                        |
 * | --------- | -------------------------------------------------------------- |
 * | service   | `service_start` (backend lifecycle), `mission_update`           |
 * | collector | `system_metrics`, `docker_status`, `host_inventory`, `agent_status` |
 * | heartbeat | `heartbeat`                                                     |
 * | warning   | derived severity = warning (see below)                          |
 * | error     | derived severity = error (see below)                            |
 *
 * Severity is derived, because the event stream has no severity field:
 *
 * - **error** — `asset_offline` (an asset stopped reporting).
 * - **warning** — payload signals degradation: `docker_status` with a
 *   stopped daemon or failed containers, `heartbeat` with `failures_total > 0`.
 * - **ok** — `asset_online` (recovery).
 * - **info** — everything else.
 *
 * Selected chips combine as a union; nothing selected means "show all".
 * Unknown event types stay visible under "all" — the stream is schema-free
 * by design and the timeline must never silently drop data.
 */
import type { ObservatoryEvent } from "@/types";

export type EventSeverity = "info" | "ok" | "warning" | "error";
export type EventKind = "service" | "collector" | "heartbeat" | "other";
export type EventFilter = "service" | "collector" | "heartbeat" | "warning" | "error";

export const EVENT_FILTERS: { id: EventFilter; label: string }[] = [
  { id: "service", label: "Service" },
  { id: "collector", label: "Collector" },
  { id: "heartbeat", label: "Heartbeat" },
  { id: "warning", label: "Warning" },
  { id: "error", label: "Error" },
];

const KIND_BY_TYPE: Record<string, EventKind> = {
  service_start: "service",
  mission_update: "service",
  system_metrics: "collector",
  docker_status: "collector",
  host_inventory: "collector",
  agent_status: "collector",
  heartbeat: "heartbeat",
  asset_offline: "other",
  asset_online: "other",
};

const TITLE_BY_TYPE: Record<string, string> = {
  heartbeat: "Heartbeat",
  system_metrics: "System metrics reported",
  docker_status: "Docker telemetry reported",
  agent_status: "Agent status reported",
  host_inventory: "Host inventory reported",
  mission_update: "Mission update",
  asset_offline: "Asset went offline",
  asset_online: "Asset back online",
  service_start: "Service started",
};

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function eventKind(event: ObservatoryEvent): EventKind {
  return KIND_BY_TYPE[event.event_type] ?? "other";
}

export function eventSeverity(event: ObservatoryEvent): EventSeverity {
  const payload = event.payload;
  switch (event.event_type) {
    case "asset_offline":
      return "error";
    case "asset_online":
      return "ok";
    case "docker_status": {
      const failed = asNumber(payload["containers_failed"]) ?? 0;
      return payload["daemon_running"] === false || failed > 0 ? "warning" : "info";
    }
    case "heartbeat": {
      const failures = asNumber(payload["failures_total"]) ?? 0;
      return failures > 0 ? "warning" : "info";
    }
    default:
      return "info";
  }
}

/** Human title for an event; unknown types fall back to the raw type. */
export function eventTitle(event: ObservatoryEvent): string {
  return TITLE_BY_TYPE[event.event_type] ?? event.event_type;
}

/**
 * One short, factual detail line derived from well-known payload fields —
 * never a payload dump (payloads are schema-free and rendered inert).
 */
export function eventDetail(event: ObservatoryEvent): string | null {
  const payload = event.payload;
  switch (event.event_type) {
    case "docker_status": {
      if (payload["daemon_running"] === false) return "Docker daemon not running";
      const running = asNumber(payload["containers_running"]);
      const total = asNumber(payload["containers_total"]);
      const failed = asNumber(payload["containers_failed"]) ?? 0;
      if (running === null || total === null) return null;
      const base = `${running} of ${total} containers running`;
      return failed > 0 ? `${base}, ${failed} failed` : base;
    }
    case "heartbeat": {
      const failures = asNumber(payload["failures_total"]) ?? 0;
      const version = asString(payload["collector_version"]);
      const parts: string[] = [];
      if (version) parts.push(`collector ${version}`);
      if (failures > 0) parts.push(`${failures} failure${failures === 1 ? "" : "s"} reported`);
      return parts.length > 0 ? parts.join(" · ") : null;
    }
    case "system_metrics": {
      const cpu = asNumber(payload["cpu_percent"]);
      const memory = payload["memory"];
      const memoryPercent =
        typeof memory === "object" && memory !== null
          ? asNumber((memory as Record<string, unknown>)["used_percent"])
          : null;
      const parts: string[] = [];
      if (cpu !== null) parts.push(`CPU ${cpu.toFixed(1)}%`);
      if (memoryPercent !== null) parts.push(`RAM ${memoryPercent.toFixed(1)}%`);
      return parts.length > 0 ? parts.join(" · ") : null;
    }
    case "mission_update": {
      const mission = asString(payload["mission_id"]);
      const state = asString(payload["state"]);
      if (!mission) return null;
      return state ? `${mission} → ${state}` : mission;
    }
    case "service_start": {
      const version = asString(payload["version"]);
      return version ? `version ${version}` : null;
    }
    case "asset_offline":
    case "asset_online": {
      const asset = asString(payload["fleet_id"]) ?? asString(payload["asset_id"]);
      return asset;
    }
    default:
      return null;
  }
}

/** Apply the selected chips (union; empty set = show everything). */
export function filterEvents(
  events: ObservatoryEvent[],
  active: ReadonlySet<EventFilter>,
): ObservatoryEvent[] {
  if (active.size === 0) return events;
  return events.filter((event) => {
    const kind = eventKind(event);
    const severity = eventSeverity(event);
    if (active.has("service") && kind === "service") return true;
    if (active.has("collector") && kind === "collector") return true;
    if (active.has("heartbeat") && kind === "heartbeat") return true;
    if (active.has("warning") && severity === "warning") return true;
    if (active.has("error") && severity === "error") return true;
    return false;
  });
}

/**
 * Present events in source-time order (newest first). The backend orders by
 * *ingestion* time — operationally correct for the stream, but a timeline
 * displays source timestamps, so a late-arriving or backfilled event must
 * still slot into its true position. Ties break on ingestion time.
 */
export function sortEventsNewestFirst(events: ObservatoryEvent[]): ObservatoryEvent[] {
  return [...events].sort(
    (a, b) => b.timestamp.localeCompare(a.timestamp) || b.received_at.localeCompare(a.received_at),
  );
}
