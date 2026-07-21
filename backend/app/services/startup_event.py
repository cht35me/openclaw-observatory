"""Backend service-start event (Mission M003.5 §4).

The Recent Events monitor section shows *lifecycle* events. Collector
lifecycles are visible through offline/online transitions, but the backend's
own restarts were previously invisible: it emits heartbeats immediately, so
no offline gap appears for quick restarts. Recording an explicit
``service_start`` event on every successful startup makes deploys and
restarts first-class operational history.

Like offline transitions (:mod:`app.services.offline`), the event originates
*inside* the backend and is inserted directly — it never passes API-key
authentication because it is not collector telemetry.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.config import Settings
from app.models.event import Event
from app.storage.base import EventStorage
from app.version import GIT_COMMIT

SERVICE_START_EVENT_TYPE = "service_start"


async def record_service_start(settings: Settings, events: EventStorage) -> Event:
    """Insert one ``service_start`` event for this backend boot."""
    now = datetime.now(UTC)
    event = Event(
        id=uuid4(),
        collector_id=settings.fleet_id,
        timestamp=now,
        event_type=SERVICE_START_EVENT_TYPE,
        payload={
            "service": settings.app_name,
            "version": settings.app_version,
            "git_commit": GIT_COMMIT,
            "environment": settings.deployment_environment.value,
        },
        schema_version=1,
        received_at=now,
    )
    await events.insert_event(event)
    return event
