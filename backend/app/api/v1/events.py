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

from app.api.deps import MetricsDep, StorageDep
from app.auth import CollectorPrincipal, require_collector
from app.models.event import Event, EventAccepted, EventIn
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
    principal: Annotated[CollectorPrincipal, Depends(require_collector)],
) -> EventAccepted:
    """Validate, stamp, and persist a single collector event.

    Returns **202 Accepted** with the assigned event ID, **403** if the
    authenticated identity does not own the submitted ``collector_id``
    (SD-017), or **503** if the storage backend is unavailable (collectors
    retry with backoff per docs/architecture.md §4).
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

    metrics.events_ingested_total.labels(
        collector_id=event.collector_id, event_type=event.event_type
    ).inc()
    return EventAccepted(id=event.id, received_at=event.received_at)
