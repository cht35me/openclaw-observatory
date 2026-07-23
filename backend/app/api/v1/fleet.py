"""Read-only Fleet Registry API (Mission M003 §7).

``GET /api/v1/fleet`` and ``GET /api/v1/fleet/{fleet_id}`` return registry
identities decorated with derived telemetry (last heartbeat, connectivity,
computed health).

Read-only by design: the registry is the source of truth for identity, and no
API route creates or mutates identities — seeding/administration happens
inside the backend only (immutable Fleet IDs, M003 security requirement).

Authentication: reads require a valid collector API key (docs/security.md §3:
no anonymous read access, ever). Any authenticated fleet identity may read
the registry; per-role authorization arrives with the RBAC milestone
(architecture §2.8).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import InventoryStorageDep, RegistryServiceDep, StorageDep
from app.auth import CollectorPrincipal, require_collector
from app.models.inventory import HostInventoryRecord
from app.models.registry import FleetAssetView
from app.models.telemetry import DOCKER_STATUS_EVENT_TYPE, TelemetrySnapshot

router = APIRouter(prefix="/api/v1", tags=["fleet"])


@router.get(
    "/fleet",
    response_model=list[FleetAssetView],
    summary="List all Fleet Registry assets",
)
async def list_fleet(
    registry: RegistryServiceDep,
    _principal: Annotated[CollectorPrincipal, Depends(require_collector)],
) -> list[FleetAssetView]:
    """Return every registry asset with derived connectivity and health."""
    return await registry.list_views()


@router.get(
    "/fleet/{fleet_id}",
    response_model=FleetAssetView,
    summary="Fetch one Fleet Registry asset",
)
async def get_fleet_asset(
    fleet_id: str,
    registry: RegistryServiceDep,
    _principal: Annotated[CollectorPrincipal, Depends(require_collector)],
) -> FleetAssetView:
    """Return one registry asset, or 404 when the Fleet ID is unknown."""
    view = await registry.get_view(fleet_id)
    if view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown fleet_id.",
        )
    return view


@router.get(
    "/fleet/{fleet_id}/inventory",
    response_model=HostInventoryRecord,
    summary="Fetch the latest Host Inventory for one node",
)
async def get_host_inventory(
    fleet_id: str,
    registry: RegistryServiceDep,
    inventories: InventoryStorageDep,
    _principal: Annotated[CollectorPrincipal, Depends(require_collector)],
) -> HostInventoryRecord:
    """Return the newest ``host_inventory`` projection for one host (M003.5 §3).

    404 when the Fleet ID is unknown *or* the host has not reported
    inventory yet. This is the stored full-host model the future central
    node's enhanced Fleet & Services view renders — the local monitor keeps
    the reduced view by design (§3e).
    """
    if await registry.get_view(fleet_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown fleet_id.",
        )
    record = await inventories.get_inventory(fleet_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No host inventory reported for this fleet_id yet.",
        )
    return record


@router.get(
    "/fleet/{fleet_id}/docker-status",
    response_model=TelemetrySnapshot,
    summary="Fetch the latest Docker telemetry for one node",
)
async def get_docker_status(
    fleet_id: str,
    registry: RegistryServiceDep,
    events: StorageDep,
    _principal: Annotated[CollectorPrincipal, Depends(require_collector)],
) -> TelemetrySnapshot:
    """Return the newest ``docker_status`` event for one host (M004 PR3).

    Constrained-by-design (supervisor gate): this is a dedicated route for
    exactly one allowlisted telemetry type, not a generic event browser — the
    event stream itself stays internal. 404 when the Fleet ID is unknown
    *or* the host has not reported Docker telemetry yet (a normal condition
    for assets without the docker capability); consumers branch on it,
    never retry.
    """
    if await registry.get_view(fleet_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown fleet_id.",
        )
    event = await events.latest_event(fleet_id, DOCKER_STATUS_EVENT_TYPE)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No docker telemetry reported for this fleet_id yet.",
        )
    return TelemetrySnapshot.from_event(fleet_id, event)
