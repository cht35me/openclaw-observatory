"""Offline detection and backend self-heartbeat (Mission M003 §5/§6).

With push-based collectors (SD-002) there is no probe to fail; offline means
*absence of heartbeat*. The :class:`OfflineDetector` periodically scans the
Fleet Registry, judges each asset's newest heartbeat against
``OFFLINE_TIMEOUT``, and records transitions as events in the same event
stream as all other telemetry:

* ``asset_offline`` — a previously reporting asset stopped heartbeating;
* ``asset_online``  — a silent asset resumed (recovery).

Transition events carry the Observatory's own fleet identity in
``detected_by`` and are inserted internally (they originate from the backend,
not from a collector, so they do not pass API-key authentication — the
network write path for collectors remains unchanged).

State semantics:

* assets that have *never* heartbeated are ``unknown`` — they produce gauge
  visibility but no transition events (avoids a spurious OFFLINE storm right
  after seeding a fresh registry);
* judgments use **source timestamps**, so replayed old heartbeats cannot fake
  liveness (see :mod:`app.services.pipeline`).

The module also emits the backend's own heartbeat (``OBLN01`` — the local
Observatory deployment's service identity, FLEET.md) so the Observatory is
visible — and offline-detectable — in its own registry.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from app.config import Settings
from app.metrics import AppMetrics
from app.models.event import Event
from app.models.heartbeat import HEARTBEAT_EVENT_TYPE
from app.models.registry import Connectivity
from app.storage.base import EventStorage, RegistryStorage, StorageError

_logger = logging.getLogger("observatory.offline")

OFFLINE_EVENT_TYPE = "asset_offline"
ONLINE_EVENT_TYPE = "asset_online"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class OfflineDetector:
    """Registry scanner: derives connectivity, emits transition events."""

    def __init__(
        self,
        settings: Settings,
        registry: RegistryStorage,
        events: EventStorage,
        metrics: AppMetrics,
        now_fn: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._events = events
        self._metrics = metrics
        self._now_fn = now_fn
        #: Last known connectivity per fleet_id (baseline set on first scan).
        self._known: dict[str, Connectivity] = {}

    async def run_once(self) -> None:
        """Perform one detection sweep (also the unit-testable entry point)."""
        now = self._now_fn()
        assets = await self._registry.list_assets()

        counts = {state: 0 for state in Connectivity}
        for asset in assets:
            state, last_heartbeat = await self._evaluate(asset.fleet_id, now)
            counts[state] += 1
            previous = self._known.get(asset.fleet_id)
            self._known[asset.fleet_id] = state
            if previous is None or previous == state:
                continue
            if state is Connectivity.OFFLINE:
                await self._emit_transition(
                    asset.fleet_id, OFFLINE_EVENT_TYPE, previous, state,
                    last_heartbeat, now,
                )
            elif state is Connectivity.ONLINE:
                await self._emit_transition(
                    asset.fleet_id, ONLINE_EVENT_TYPE, previous, state,
                    last_heartbeat, now,
                )

        self._metrics.fleet_registered_assets.set(len(assets))
        self._metrics.fleet_active_assets.set(counts[Connectivity.ONLINE])
        self._metrics.fleet_offline_assets.set(counts[Connectivity.OFFLINE])
        self._metrics.fleet_unknown_assets.set(counts[Connectivity.UNKNOWN])

    async def _evaluate(
        self, fleet_id: str, now: datetime
    ) -> tuple[Connectivity, datetime | None]:
        heartbeat = await self._events.latest_event(fleet_id, HEARTBEAT_EVENT_TYPE)
        if heartbeat is None:
            return Connectivity.UNKNOWN, None
        age = (now - heartbeat.timestamp).total_seconds()
        if age > self._settings.offline_timeout:
            return Connectivity.OFFLINE, heartbeat.timestamp
        return Connectivity.ONLINE, heartbeat.timestamp

    async def _emit_transition(
        self,
        fleet_id: str,
        event_type: str,
        previous: Connectivity,
        current: Connectivity,
        last_heartbeat: datetime | None,
        now: datetime,
    ) -> None:
        event = Event(
            id=uuid4(),
            collector_id=fleet_id,
            timestamp=now,
            event_type=event_type,
            payload={
                "previous": previous.value,
                "current": current.value,
                "last_heartbeat_timestamp": (
                    last_heartbeat.isoformat() if last_heartbeat else None
                ),
                "offline_timeout_seconds": self._settings.offline_timeout,
                "detected_by": self._settings.fleet_id,
            },
            schema_version=1,
            received_at=now,
        )
        await self._events.insert_event(event)
        direction = "offline" if event_type == OFFLINE_EVENT_TYPE else "online"
        self._metrics.offline_transitions_total.labels(
            collector_id=fleet_id, direction=direction
        ).inc()
        log = _logger.warning if direction == "offline" else _logger.info
        log(
            f"asset went {direction}",
            extra={"collector_id": fleet_id, "event_id": str(event.id)},
        )

    async def run_forever(self) -> None:
        """Loop at ``offline_check_interval``; storage errors are logged, not fatal."""
        while True:
            try:
                await self.run_once()
            except StorageError:
                _logger.exception("offline detection sweep failed; will retry")
            except asyncio.CancelledError:  # pragma: no cover - shutdown path
                raise
            await asyncio.sleep(self._settings.offline_check_interval)


class BackendHeartbeat:
    """Emits the Observatory backend's own heartbeat (M003 §1: OBLN01)."""

    def __init__(
        self,
        settings: Settings,
        events: EventStorage,
        uptime_fn: Callable[[], float],
        now_fn: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._settings = settings
        self._events = events
        self._uptime_fn = uptime_fn
        self._now_fn = now_fn

    async def beat_once(self) -> Event:
        now = self._now_fn()
        event = Event(
            id=uuid4(),
            collector_id=self._settings.fleet_id,
            timestamp=now,
            event_type=HEARTBEAT_EVENT_TYPE,
            payload={
                "collector_type": "observatory-backend",
                "collector_version": self._settings.app_version,
                "software_version": self._settings.app_version,
                "uptime_seconds": round(self._uptime_fn(), 3),
                "failures_total": 0,
            },
            schema_version=1,
            received_at=now,
        )
        await self._events.insert_event(event)
        return event

    async def run_forever(self) -> None:
        """Loop at ``heartbeat_interval``; storage errors are logged, not fatal."""
        while True:
            try:
                await self.beat_once()
            except StorageError:
                _logger.warning("backend self-heartbeat failed; storage unavailable")
            except asyncio.CancelledError:  # pragma: no cover - shutdown path
                raise
            await asyncio.sleep(self._settings.heartbeat_interval)
