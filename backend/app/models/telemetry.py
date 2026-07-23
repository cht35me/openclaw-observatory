"""Latest-telemetry read models (Mission M004 PR3, additive).

The event stream stores arbitrary typed telemetry per asset; the monitor
consumes it internally, but until M004 no REST route exposed "the newest
event of one type for one asset". :class:`TelemetrySnapshot` is that read
model: the newest stored event of a given type, with its source timestamp and
declared payload schema version, so consumers can reason about freshness and
shape.

Deliberately constrained (supervisor-gated contract): only an explicit
server-side allowlist of event types is ever served — today exactly
``docker_status`` via ``GET /api/v1/fleet/{fleet_id}/docker-status``. The
payload is passed through as stored (rendered inert by consumers, never
interpreted — docs/security.md §9).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.event import Event

#: Event type carrying Docker daemon/container telemetry (M003 §10).
DOCKER_STATUS_EVENT_TYPE = "docker_status"

#: Server-side allowlist of telemetry types exposed over REST (M004 PR3
#: supervisor gate): the generic event stream stays internal; only these
#: types get a read route. Extend deliberately, one review at a time.
EXPOSED_TELEMETRY_TYPES: tuple[str, ...] = (DOCKER_STATUS_EVENT_TYPE,)


class TelemetrySnapshot(BaseModel):
    """Newest stored telemetry event of one type for one fleet asset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fleet_id: str
    event_type: str
    #: Source timestamp of the event (collector clock, normalized UTC).
    timestamp: datetime
    #: Ingestion timestamp stamped by the backend.
    received_at: datetime
    #: Payload schema version declared by the collector (SD-004).
    schema_version: int
    payload: dict[str, Any]

    @classmethod
    def from_event(cls, fleet_id: str, event: Event) -> TelemetrySnapshot:
        """Project one stored event into the snapshot read model."""
        return cls(
            fleet_id=fleet_id,
            event_type=event.event_type,
            timestamp=event.timestamp,
            received_at=event.received_at,
            schema_version=event.schema_version,
            payload=event.payload,
        )
