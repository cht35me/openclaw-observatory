"""Observatory Monitor route (``GET /monitor``).

Server-rendered instrument panel for the local deployment (SD-020,
proposed). Like ``/health`` (SD-013) and ``/metrics`` (SD-014), the page is
served without API-key auth and protected by network boundary instead: the
backend binds to loopback and is reachable only on-host or over the private
tailnet (SD-003). It is strictly read-only — it renders the same read models
the authenticated ``/api/v1`` routes expose, and never mutates anything.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.api.deps import MissionStorageDep, RegistryServiceDep, SettingsDep, StorageDep
from app.services.monitor import build_snapshot, render_monitor_html

router = APIRouter()


@router.get("/monitor", response_class=HTMLResponse, tags=["operations"])
async def monitor(
    request: Request,
    settings: SettingsDep,
    registry: RegistryServiceDep,
    missions: MissionStorageDep,
    storage: StorageDep,
) -> HTMLResponse:
    """Render the Observatory instrument panel."""
    uptime = time.monotonic() - request.app.state.started_at_monotonic
    snapshot = await build_snapshot(
        settings=settings,
        registry=registry,
        missions=missions,
        events=storage,
        uptime_seconds=uptime,
    )
    return HTMLResponse(render_monitor_html(snapshot))
