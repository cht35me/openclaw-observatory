"""Fleet Registry read-model assembly (Mission M003 §1/§7/§9).

Joins the two cleanly separated domains at read time:

* **identity** from :class:`~app.storage.base.RegistryStorage` (authoritative
  inventory, seeded from FLEET.md);
* **telemetry** from the event stream (newest ``heartbeat`` and
  ``system_metrics`` events per asset).

Derived fields — last heartbeat, connectivity, live software version, and the
computed health score — are never stored on the registry record, so identity
stays low-churn and telemetry stays append-only.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.config import Settings
from app.models.heartbeat import HEARTBEAT_EVENT_TYPE
from app.models.registry import (
    Connectivity,
    FleetAsset,
    FleetAssetView,
    HeartbeatInfo,
)
from app.services.health import compute_health
from app.storage.base import EventStorage, RegistryStorage

#: Event type carrying host system telemetry (used for health scoring).
SYSTEM_METRICS_EVENT_TYPE = "system_metrics"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RegistryService:
    """Builds API read-models for registry assets."""

    def __init__(
        self,
        settings: Settings,
        registry: RegistryStorage,
        events: EventStorage,
        now_fn: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._events = events
        self._now_fn = now_fn

    async def get_view(self, fleet_id: str) -> FleetAssetView | None:
        asset = await self._registry.get_asset(fleet_id)
        if asset is None:
            return None
        return await self._build_view(asset)

    async def list_views(self) -> list[FleetAssetView]:
        assets = await self._registry.list_assets()
        return [await self._build_view(asset) for asset in assets]

    async def _build_view(self, asset: FleetAsset) -> FleetAssetView:
        now = self._now_fn()

        heartbeat_event = await self._events.latest_event(
            asset.fleet_id, HEARTBEAT_EVENT_TYPE
        )
        heartbeat: HeartbeatInfo | None = None
        heartbeat_age: float | None = None
        collector_failures: int | None = None
        if heartbeat_event is not None:
            payload = heartbeat_event.payload or {}
            software_version = payload.get("software_version")
            collector_version = payload.get("collector_version")
            collector_type = payload.get("collector_type")
            failures = payload.get("failures_total")
            heartbeat = HeartbeatInfo(
                timestamp=heartbeat_event.timestamp,
                received_at=heartbeat_event.received_at,
                software_version=(
                    software_version if isinstance(software_version, str) else None
                ),
                collector_version=(
                    collector_version if isinstance(collector_version, str) else None
                ),
                collector_type=(
                    collector_type if isinstance(collector_type, str) else None
                ),
                schema_version=heartbeat_event.schema_version,
            )
            heartbeat_age = (now - heartbeat_event.timestamp).total_seconds()
            if isinstance(failures, int) and not isinstance(failures, bool):
                collector_failures = failures

        if heartbeat is None:
            connectivity = Connectivity.UNKNOWN
        elif heartbeat_age is not None and heartbeat_age > self._settings.offline_timeout:
            connectivity = Connectivity.OFFLINE
        else:
            connectivity = Connectivity.ONLINE

        system_event = await self._events.latest_event(
            asset.fleet_id, SYSTEM_METRICS_EVENT_TYPE
        )
        health = compute_health(
            self._settings,
            connectivity=connectivity,
            heartbeat_age_seconds=heartbeat_age,
            system_payload=system_event.payload if system_event else None,
            collector_failures=collector_failures,
        )

        return FleetAssetView(
            fleet_id=asset.fleet_id,
            asset_type=asset.asset_type,
            nickname=asset.nickname,
            hostname=asset.hostname,
            role=asset.role,
            location=asset.location,
            platform=asset.platform,
            os=asset.os,
            software_version=(
                (heartbeat.software_version if heartbeat else None)
                or asset.software_version
            ),
            host_fleet_id=asset.host_fleet_id,
            deployment_role=asset.deployment_role,
            service_version=asset.service_version,
            capabilities=asset.capabilities,
            tags=asset.tags,
            status=asset.status,
            registered_at=asset.registered_at,
            updated_at=asset.updated_at,
            last_heartbeat=heartbeat,
            connectivity=connectivity,
            health=health,
        )
