"""Version 1 of the ingestion API (SD-004: URL-prefix versioning).

Each module in this package owns an ``APIRouter`` with the full ``/api/v1``
prefix baked in (so route templates used in metrics/OpenAPI are complete);
``routers`` aggregates them for registration in the app factory. Additive
changes only within v1; breaking changes require ``/api/v2/``.
"""

from fastapi import APIRouter

from app.api.v1.events import router as events_router
from app.api.v1.fleet import router as fleet_router
from app.api.v1.missions import router as missions_router

#: All v1 routers, registered by :func:`app.main.create_app`.
routers: tuple[APIRouter, ...] = (events_router, fleet_router, missions_router)
