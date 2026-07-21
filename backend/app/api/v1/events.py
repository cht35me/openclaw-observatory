"""Telemetry ingestion: ``POST /api/v1/events``.

Authenticated collectors submit validated telemetry events; each event is
stamped with a UUID and ingestion timestamp and persisted through the storage
interface. Failure isolation per docs/architecture.md §3: a bad payload or a
storage outage affects only the failing request, never the pipeline.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import MetricsDep, PipelineDep, StorageDep
from app.auth import CollectorPrincipal, require_collector
from app.models.event import Event, EventAccepted, EventIn
from app.services.pipeline import PipelineRejection
from app.storage.base import StorageError

_logger = logging.getLogger("observatory.ingestion")

# The version prefix is baked into the router itself (rather than a nested
# include) so the matched route template — used for metric labels and the
# OpenAPI schema — always carries the full versioned path.
router = APIRouter(prefix="/api/v1", tags=["ingestion"])


@router.post(
    "/events",
    response_model=EventAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest one telemetry event",
)
async def ingest_event(
    inbound: EventIn,
    request: Request,
    storage: StorageDep,
    metrics: MetricsDep,
    pipeline: PipelineDep,
    principal: Annotated[CollectorPrincipal, Depends(require_collector)],
) -> EventAccepted:
    """Validate, stamp, and persist a single collector event.

    Returns **202 Accepted** with the assigned event ID, **403** if the
    authenticated identity does not own the submitted ``collector_id``
    (SD-017), **409/422** if an event-type handler rejects the payload or a
    mission transition (M003), or **503** if the storage backend is
    unavailable (collectors retry with backoff per docs/architecture.md §4).
    """
    # Expose the collector identity to the request-logging middleware.
    request.state.collector_id = inbound.collector_id

    # SD-017: each API key is bound to exactly one Fleet identity; a collector
    # may only submit telemetry for its own collector_id (anti-spoofing).
    if inbound.collector_id != principal.subject:
        metrics.events_ingestion_failures_total.labels(reason="identity_mismatch").inc()
        _logger.warning(
            "collector identity mismatch rejected",
            extra={
                "collector_id": inbound.collector_id,
                "authenticated_subject": principal.subject,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key is not authorized for this collector_id.",
        )

    # M003: event types with server-side semantics (heartbeat,
    # mission_update) get pre-persistence validation so invalid payloads and
    # illegal mission transitions never enter the event stream.
    try:
        await pipeline.validate(inbound)
    except PipelineRejection as rejection:
        metrics.events_ingestion_failures_total.labels(reason=rejection.reason).inc()
        _logger.warning(
            "event rejected by pipeline handler",
            extra={"collector_id": inbound.collector_id},
        )
        raise HTTPException(status_code=rejection.status_code, detail=rejection.detail) from None

    event = Event.from_ingest(inbound)
    try:
        await storage.insert_event(event)
    except StorageError:
        metrics.events_ingestion_failures_total.labels(reason="storage_error").inc()
        _logger.exception(
            "event persistence failed",
            extra={"collector_id": inbound.collector_id, "event_id": str(event.id)},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage backend unavailable; retry later.",
        ) from None

    # Post-persistence projections (mission state, heartbeat metrics). A
    # failure here yields 503 so the collector retries; handlers are
    # idempotent under retry (the event itself is already stored).
    try:
        await pipeline.apply(event)
    except StorageError:
        metrics.events_ingestion_failures_total.labels(reason="projection_error").inc()
        _logger.exception(
            "event projection failed",
            extra={"collector_id": inbound.collector_id, "event_id": str(event.id)},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage backend unavailable; retry later.",
        ) from None

    metrics.events_ingested_total.labels(
        collector_id=event.collector_id, event_type=event.event_type
    ).inc()
    return EventAccepted(id=event.id, received_at=event.received_at)
