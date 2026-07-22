/**
 * Mirrors backend/app/models/mission.py (Mission M003 §4).
 * MissionView is the read model returned by GET /api/v1/missions.
 */

/** Ordered lifecycle states (linear, forward-only). */
export const MISSION_STATES = [
  "Created",
  "Queued",
  "Assigned",
  "Running",
  "Review",
  "Completed",
] as const;

export type MissionState = (typeof MISSION_STATES)[number];

export interface MissionView {
  mission_id: string;
  title: string;
  assigned_agent: string | null;
  /** One of MISSION_STATES; typed as string to stay tolerant of additive backend change. */
  state: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  pr_ref: string | null;
  commit_sha: string | null;
  updated_at: string;
}
