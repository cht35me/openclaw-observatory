"""Health endpoint.

Design decision — ``/health`` always returns **HTTP 200** with a ``status``
field (``"ok"`` or ``"degraded"``) rather than 503 when ClickHouse is
unreachable:

* The endpoint reports on the API *process*; a database outage degrades
  ingestion but the service itself is alive and must not be restarted by
  liveness probes reacting to 503s (that would turn a database incident into
  a crash loop).
* Machine consumers get an unambiguous signal via ``status`` and
  ``database.connected``; alerting keys off those fields and off the
  ``observatory_db_latency_seconds`` / ingestion-failure metrics.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.deps import SettingsDep, StorageDep

router = APIRouter()


class DatabaseHealth(BaseModel):
    """Connectivity summary for the storage backend."""

    connected: bool


class HealthResponse(BaseModel):
    """Response schema for ``GET /health``."""

    status: str
    version: str
    uptime_seconds: float
    database: DatabaseHealth


@router.get("/health", response_model=HealthResponse, tags=["operations"])
async def health(request: Request, settings: SettingsDep, storage: StorageDep) -> HealthResponse:
    """Report service status, version, uptime, and database connectivity."""
    connected = await storage.ping()
    uptime = time.monotonic() - request.app.state.started_at_monotonic
    return HealthResponse(
        status="ok" if connected else "degraded",
        version=settings.app_version,
        uptime_seconds=round(uptime, 3),
        database=DatabaseHealth(connected=connected),
    )
