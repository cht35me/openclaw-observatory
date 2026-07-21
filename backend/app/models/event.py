"""Canonical telemetry event model (Mission M002 §6) and API schemas.

``EventIn`` is the wire format accepted by ``POST /api/v1/events``; ``Event``
is the canonical, storage-facing record the Observatory stamps at ingestion
(adds ``id`` and ``received_at``). Keeping the two separate means the wire
contract can evolve per API version while storage keeps a single canonical
shape (SD-004 versioning discipline).

Validation is strict: unknown fields are rejected (``extra="forbid"``),
identifiers are length- and charset-constrained, and timestamps must be
timezone-aware (normalized to UTC). Free-text/payload content is stored as
data only and never interpreted (docs/security.md §9).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

#: Constrained identifier used for collector_id and event_type: printable,
#: no whitespace or control characters, bounded length.
Identifier = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


class EventIn(BaseModel):
    """Inbound synthetic telemetry payload for ``POST /api/v1/events``.

    Example::

        {
          "collector_id": "demo",
          "timestamp": "2026-07-19T12:00:00Z",
          "event_type": "synthetic",
          "payload": {"temperature": 41, "status": "ok"}
        }
    """

    model_config = ConfigDict(extra="forbid")

    collector_id: Identifier
    timestamp: AwareDatetime = Field(
        description="Source timestamp; must be timezone-aware (e.g. ISO-8601 with 'Z')."
    )
    event_type: Identifier
    payload: dict[str, Any] = Field(description="Arbitrary JSON object with the event body.")
    schema_version: int = Field(
        default=1,
        ge=1,
        description="Payload schema version declared by the collector (SD-004).",
    )

    @field_validator("timestamp")
    @classmethod
    def _normalize_to_utc(cls, value: datetime) -> datetime:
        """Normalize aware timestamps to UTC for canonical storage."""
        return value.astimezone(UTC)


class Event(BaseModel):
    """Canonical stored event: the wire payload plus ingestion stamps."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    collector_id: str
    timestamp: datetime
    event_type: str
    payload: dict[str, Any]
    schema_version: int
    received_at: datetime

    @classmethod
    def from_ingest(cls, inbound: EventIn) -> Event:
        """Stamp an inbound payload with identity and ingestion time."""
        return cls(
            id=uuid4(),
            collector_id=inbound.collector_id,
            timestamp=inbound.timestamp,
            event_type=inbound.event_type,
            payload=inbound.payload,
            schema_version=inbound.schema_version,
            received_at=datetime.now(UTC),
        )


class EventAccepted(BaseModel):
    """Response body confirming an accepted event."""

    id: UUID
    received_at: datetime
    status: str = "accepted"
