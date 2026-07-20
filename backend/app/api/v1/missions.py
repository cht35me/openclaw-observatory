"""Read-only missions API (Mission M003 §7).

``GET /api/v1/missions`` and ``GET /api/v1/missions/{mission_id}`` expose the
mission current-state projections. Mission state *changes* are not accepted
here — they arrive as ``mission_update`` telemetry events through the
authenticated ingestion path (``POST /api/v1/events``), where transitions are
validated and recorded (see :mod:`app.services.pipeline`).

Authentication mirrors the fleet routes: valid collector API key required,
no anonymous reads (docs/security.md §3).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import MissionStorageDep
from app.auth import CollectorPrincipal, require_collector
from app.models.mission import MissionView

router = APIRouter(prefix="/api/v1", tags=["missions"])


@router.get(
    "/missions",
    response_model=list[MissionView],
    summary="List all tracked missions",
)
async def list_missions(
    missions: MissionStorageDep,
    _principal: Annotated[CollectorPrincipal, Depends(require_collector)],
) -> list[MissionView]:
    """Return every mission with lifecycle state and computed duration."""
    return [MissionView.from_record(record) for record in await missions.list_missions()]


@router.get(
    "/missions/{mission_id}",
    response_model=MissionView,
    summary="Fetch one mission",
)
async def get_mission(
    mission_id: str,
    missions: MissionStorageDep,
    _principal: Annotated[CollectorPrincipal, Depends(require_collector)],
) -> MissionView:
    """Return one mission, or 404 when the mission ID is unknown."""
    record = await missions.get_mission(mission_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown mission_id.",
        )
    return MissionView.from_record(record)
