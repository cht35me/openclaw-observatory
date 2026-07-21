"""Per-event-type ingestion handlers (Mission M003).

The ingestion route stays generic — every telemetry payload flows through the
same authenticated, validated event pipeline (M002) — while event types with
server-side semantics get a registered handler here (SD-008 module
discipline: new collectors/event types plug in without touching the route).

Contract:

* ``validate`` runs **before** the event is persisted and must be free of
  side effects; it may reject the request (:class:`PipelineRejection`), so
  invalid heartbeats or illegal mission transitions never enter the event
  stream.
* ``apply`` runs **after** the event is persisted and performs projections /
  metrics (mission record upsert, heartbeat gauges). A failing ``apply``
  surfaces as 503 so the collector retries; handlers are idempotent under
  retry.

Event types without a handler are stored as-is (generic telemetry).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from app.config import Settings
from app.metrics import AppMetrics
from app.models.event import Event, EventIn
from app.models.heartbeat import HEARTBEAT_EVENT_TYPE, HeartbeatPayload
from app.models.inventory import HOST_INVENTORY_EVENT_TYPE, HostInventoryRecord
from app.models.mission import (
    MISSION_STATES,
    MissionRecord,
    MissionUpdate,
    is_valid_transition,
)
from app.storage.base import HostInventoryStorage, MissionStorage, RegistryStorage

_logger = logging.getLogger("observatory.pipeline")

#: Event type carrying mission lifecycle transitions.
MISSION_UPDATE_EVENT_TYPE = "mission_update"

#: Maximum tolerated source-clock skew into the future. Replay/staleness
#: protection: liveness is judged on source timestamps, so replayed (old)
#: heartbeats cannot fake liveness; forged *future* timestamps could, and are
#: rejected here.
MAX_FUTURE_SKEW = timedelta(minutes=5)

_RUNNING_INDEX = MISSION_STATES.index("Running")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PipelineRejection(Exception):
    """Raised by handlers to reject an inbound event before persistence."""

    def __init__(self, status_code: int, detail: str, reason: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        #: Label for the ingestion-failure metric.
        self.reason = reason


class EventHandler(ABC):
    """Server-side semantics for one event type."""

    #: The event_type this handler owns.
    event_type: str

    @abstractmethod
    async def validate(self, inbound: EventIn) -> None:
        """Reject invalid payloads/transitions. Must be side-effect free."""

    @abstractmethod
    async def apply(self, event: Event) -> None:
        """Post-persistence projections and metrics. Idempotent under retry."""


class HeartbeatHandler(EventHandler):
    """Validates heartbeat payloads and feeds heartbeat metrics (M003 §5)."""

    event_type = HEARTBEAT_EVENT_TYPE

    def __init__(
        self,
        registry: RegistryStorage,
        metrics: AppMetrics,
        now_fn: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._registry = registry
        self._metrics = metrics
        self._now_fn = now_fn

    async def validate(self, inbound: EventIn) -> None:
        try:
            HeartbeatPayload.model_validate(inbound.payload)
        except ValidationError as exc:
            raise PipelineRejection(
                status_code=422,
                detail=f"Invalid heartbeat payload: {exc.error_count()} error(s).",
                reason="validation_error",
            ) from exc
        if inbound.timestamp > self._now_fn() + MAX_FUTURE_SKEW:
            raise PipelineRejection(
                status_code=422,
                detail="Heartbeat timestamp is too far in the future.",
                reason="timestamp_skew",
            )
        # Registry is the source of truth for identity (M003 §1): heartbeats
        # for identities the registry does not know are refused — collectors
        # can never create fleet identities by reporting telemetry.
        if await self._registry.get_asset(inbound.collector_id) is None:
            raise PipelineRejection(
                status_code=403,
                detail="Unknown fleet identity; not present in the Fleet Registry.",
                reason="unknown_fleet_id",
            )

    async def apply(self, event: Event) -> None:
        payload = HeartbeatPayload.model_validate(event.payload)
        latency = (event.received_at - event.timestamp).total_seconds()
        self._metrics.heartbeat_latency_seconds.labels(collector_id=event.collector_id).observe(
            max(latency, 0.0)
        )
        self._metrics.heartbeats_received_total.labels(
            collector_id=event.collector_id,
            collector_type=payload.collector_type,
        ).inc()
        self._metrics.collector_reported_failures.labels(collector_id=event.collector_id).set(
            payload.failures_total
        )


class HostInventoryHandler(EventHandler):
    """Projects ``host_inventory`` events into the latest-state store (M003.5 §3).

    The event stream stays the durable record; this handler keeps one
    versioned row per host (SD-018) so reads never scan history. Payload
    sections are validated to be a JSON object but otherwise schema-flexible
    — collectors may add keys (SMART data, new hardware) without a backend
    release.
    """

    event_type = HOST_INVENTORY_EVENT_TYPE

    def __init__(self, registry: RegistryStorage, inventories: HostInventoryStorage) -> None:
        self._registry = registry
        self._inventories = inventories

    async def validate(self, inbound: EventIn) -> None:
        if not isinstance(inbound.payload, dict) or not inbound.payload:
            raise PipelineRejection(
                status_code=422,
                detail="host_inventory payload must be a non-empty JSON object.",
                reason="validation_error",
            )
        # Mirror the heartbeat rule: inventory describes a *registered* host;
        # collectors can never introduce identities via telemetry (M003 §1).
        if await self._registry.get_asset(inbound.collector_id) is None:
            raise PipelineRejection(
                status_code=403,
                detail="Unknown fleet identity; not present in the Fleet Registry.",
                reason="unknown_fleet_id",
            )

    async def apply(self, event: Event) -> None:
        record = HostInventoryRecord(
            fleet_id=event.collector_id,
            payload=event.payload,
            reported_at=event.timestamp,
            updated_at=event.received_at,
        )
        await self._inventories.upsert_inventory(record)
        _logger.info(
            "host inventory updated",
            extra={"collector_id": event.collector_id, "event_id": str(event.id)},
        )


class MissionUpdateHandler(EventHandler):
    """Maintains mission current-state projections (M003 §4).

    The stored ``mission_update`` event *is* the durable transition record;
    this handler additionally projects the latest state into
    :class:`~app.storage.base.MissionStorage` for fast reads.
    """

    event_type = MISSION_UPDATE_EVENT_TYPE

    def __init__(self, missions: MissionStorage) -> None:
        self._missions = missions

    async def validate(self, inbound: EventIn) -> None:
        try:
            update = MissionUpdate.model_validate(inbound.payload)
        except ValidationError as exc:
            raise PipelineRejection(
                status_code=422,
                detail=f"Invalid mission_update payload: {exc.error_count()} error(s).",
                reason="validation_error",
            ) from exc
        current = await self._missions.get_mission(update.mission_id)
        if not is_valid_transition(
            current.state if current else None, update.state, backfill=update.backfill
        ):
            current_state = current.state if current else "<new>"
            raise PipelineRejection(
                status_code=409,
                detail=(
                    f"Illegal mission transition {current_state} -> {update.state}; "
                    f"normal operation advances one state at a time along "
                    f"{' -> '.join(MISSION_STATES)} (new missions enter at Created). "
                    "Privileged backfill/recovery (backfill=true) may enter at or "
                    "jump forward to a later state; regression is never allowed "
                    "and Completed is terminal."
                ),
                reason="invalid_mission_transition",
            )
        if update.backfill:
            # Audit trail for privileged transitions (security.md structured
            # audit logging): backfill is exceptional, so every use is logged.
            _logger.info(
                "privileged mission backfill transition accepted",
                extra={
                    "mission_id": update.mission_id,
                    "from_state": current.state if current else None,
                    "to_state": update.state,
                    "collector_id": inbound.collector_id,
                },
            )

    async def apply(self, event: Event) -> None:
        update = MissionUpdate.model_validate(event.payload)
        current = await self._missions.get_mission(update.mission_id)

        created_at = current.created_at if current else event.timestamp
        started_at = current.started_at if current else None
        completed_at = current.completed_at if current else None

        state_index = MISSION_STATES.index(update.state)
        if started_at is None and state_index >= _RUNNING_INDEX:
            started_at = event.timestamp
        if update.state == "Completed" and completed_at is None:
            completed_at = event.timestamp

        record = MissionRecord(
            mission_id=update.mission_id,
            title=update.title or (current.title if current else update.mission_id),
            assigned_agent=update.assigned_agent or (current.assigned_agent if current else None),
            state=update.state,
            created_at=created_at,
            started_at=started_at,
            completed_at=completed_at,
            pr_ref=update.pr_ref or (current.pr_ref if current else None),
            commit_sha=update.commit_sha or (current.commit_sha if current else None),
            updated_at=event.received_at,
        )
        await self._missions.upsert_mission(record)
        _logger.info(
            "mission state updated",
            extra={
                "collector_id": event.collector_id,
                "event_id": str(event.id),
            },
        )


class EventPipeline:
    """Dispatches inbound events to their registered handler, if any."""

    def __init__(self, handlers: tuple[EventHandler, ...]) -> None:
        self._handlers: dict[str, EventHandler] = {
            handler.event_type: handler for handler in handlers
        }

    async def validate(self, inbound: EventIn) -> None:
        handler = self._handlers.get(inbound.event_type)
        if handler is not None:
            await handler.validate(inbound)

    async def apply(self, event: Event) -> None:
        handler = self._handlers.get(event.event_type)
        if handler is not None:
            await handler.apply(event)


def build_pipeline(
    settings: Settings,  # noqa: ARG001 - reserved for future handler config
    registry: RegistryStorage,
    missions: MissionStorage,
    metrics: AppMetrics,
    inventories: HostInventoryStorage,
    now_fn: Callable[[], datetime] = _utcnow,
) -> EventPipeline:
    """Assemble the default handler set."""
    return EventPipeline(
        (
            HeartbeatHandler(registry, metrics, now_fn=now_fn),
            MissionUpdateHandler(missions),
            HostInventoryHandler(registry, inventories),
        )
    )
