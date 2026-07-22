/** Mirrors backend/app/api/health.py (GET /health, unauthenticated — SD-013). */

export interface DatabaseHealth {
  connected: boolean;
}

export interface HealthResponse {
  /** "ok" | "degraded" — always HTTP 200 by design (see backend docstring). */
  status: string;
  version: string;
  uptime_seconds: number;
  database: DatabaseHealth;
}
