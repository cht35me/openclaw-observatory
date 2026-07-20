"""Heartbeat payload schema (Mission M003 §5).

Heartbeats travel through the same event pipeline as all other telemetry
(``event_type = "heartbeat"``); this model validates the payload strictly so
malformed heartbeats are rejected at ingestion (M003 security requirement:
validated telemetry schema).

Wire-level fields ``collector_id`` (= Fleet ID), ``timestamp``, and
``schema_version`` live on the enclosing event envelope
(:class:`app.models.event.EventIn`); the payload carries the versioning
metadata that makes rolling collector upgrades observable:

* ``collector_type`` — e.g. ``raspberry``, ``openclaw-agent``;
* ``collector_version`` — the collector's own release, e.g. ``1.2.0``;
* ``software_version`` — version of the observed software/host image.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

ShortText = Annotated[str, Field(min_length=1, max_length=128)]

#: The event_type used by all heartbeat submissions.
HEARTBEAT_EVENT_TYPE = "heartbeat"


class HeartbeatPayload(BaseModel):
    """Validated payload of a ``heartbeat`` event."""

    model_config = ConfigDict(extra="forbid")

    collector_type: ShortText
    collector_version: ShortText
    software_version: ShortText | None = None
    uptime_seconds: float | None = Field(default=None, ge=0)
    failures_total: int = Field(
        default=0,
        ge=0,
        description=(
            "Cumulative count of collection/submission failures observed by "
            "the collector since it started (feeds the collector-failure "
            "metric without requiring extra endpoints)."
        ),
    )
