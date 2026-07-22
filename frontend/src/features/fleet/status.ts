/**
 * Shared status → tone mappings for restrained, non-color-only indicators
 * (mission §3 / accessibility): every tone renders as color + icon + label.
 */
import type { StatusTone } from "@/components/StatusPill";
import type { Connectivity, HealthStatus } from "@/types";

export const HEALTH_TONES: Record<HealthStatus, StatusTone> = {
  Healthy: "ok",
  Warning: "warn",
  Critical: "critical",
  Offline: "offline",
  Unknown: "unknown",
};

export const CONNECTIVITY_TONES: Record<Connectivity, StatusTone> = {
  online: "ok",
  offline: "offline",
  unknown: "unknown",
};

export const CONNECTIVITY_LABELS: Record<Connectivity, string> = {
  online: "Online",
  offline: "Offline",
  unknown: "Unknown",
};
