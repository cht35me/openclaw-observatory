/**
 * Mirrors backend/app/models/event.py (canonical telemetry event, M002 §6).
 * The UI is read-only: EventIn (the ingestion wire format) is deliberately
 * not mirrored — the console never submits telemetry.
 */

/** Canonical stored event: wire payload plus ingestion stamps. */
export interface ObservatoryEvent {
  id: string;
  collector_id: string;
  timestamp: string;
  event_type: string;
  payload: Record<string, unknown>;
  schema_version: number;
  received_at: string;
}
