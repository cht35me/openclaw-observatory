"""Fleet Registry models (Mission M003 §1).

The Fleet Registry is the authoritative inventory of all managed assets
(agents, hosts, services). Identity is defined in FLEET.md; this module is
the runtime representation.

Separation of concerns (M003 supervisor guidance):

* **Identity** lives here — Fleet ID, placement, role, capabilities, tags,
  lifecycle status. Identities are created by seeding/administration only;
  collectors can *never* create or modify them (immutable Fleet IDs).
* **Telemetry** (heartbeats, metrics) lives in the event stream. Read views
  join the two: ``FleetAssetView`` decorates an identity with derived,
  telemetry-based fields (last heartbeat, connectivity, health).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

#: Fleet IDs follow FLEET.md conventions (e.g. ``A001``, ``RPSG01``, ``OBS01``).
FleetId = Annotated[
    str,
    Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]

#: Bounded free-ish text fields (rendered inert, never interpreted —
#: docs/security.md §9).
ShortText = Annotated[str, Field(max_length=256)]

#: Capability / tag entries: short lowercase-ish tokens.
Token = Annotated[
    str,
    Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


class LifecycleStatus(StrEnum):
    """Asset lifecycle states per FLEET.md."""

    PROVISIONED = "Provisioned"
    COMMISSIONING = "Commissioning"
    ACTIVE = "Active"
    PAUSED = "Paused"
    SUSPENDED = "Suspended"
    RETIRED = "Retired"


class Connectivity(StrEnum):
    """Heartbeat-derived reachability of an asset."""

    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"  # no heartbeat ever received


class HealthStatus(StrEnum):
    """Computed health score (M003 §9)."""

    HEALTHY = "Healthy"
    WARNING = "Warning"
    CRITICAL = "Critical"
    OFFLINE = "Offline"
    UNKNOWN = "Unknown"  # no telemetry to judge from


class FleetAsset(BaseModel):
    """One Fleet Registry identity record.

    This is the *stored* shape: identity and lifecycle only. Telemetry-derived
    fields belong to :class:`FleetAssetView`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    fleet_id: FleetId
    nickname: ShortText | None = Field(
        default=None,
        description="Optional human-friendly name; cosmetic, never a key (FLEET.md).",
    )
    hostname: ShortText
    role: ShortText
    location: ShortText
    platform: ShortText
    os: ShortText
    software_version: ShortText | None = Field(
        default=None,
        description=(
            "Seeded/administrative software version; the live value is "
            "derived from heartbeats when available."
        ),
    )
    capabilities: tuple[Token, ...] = Field(
        default=(),
        description="Advertised capabilities, e.g. telemetry, heartbeat, missions, docker.",
    )
    tags: tuple[Token, ...] = Field(
        default=(),
        description="Arbitrary filter tags, e.g. production, lab, singapore, edge, critical.",
    )
    status: LifecycleStatus = LifecycleStatus.ACTIVE
    registered_at: datetime
    updated_at: datetime


class HeartbeatInfo(BaseModel):
    """Latest heartbeat details for an asset (derived from the event stream)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp: datetime
    received_at: datetime
    software_version: str | None = None
    collector_version: str | None = None
    collector_type: str | None = None
    schema_version: int | None = None


class FleetAssetView(BaseModel):
    """Read-model returned by the registry API: identity + derived telemetry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fleet_id: str
    nickname: str | None
    hostname: str
    role: str
    location: str
    platform: str
    os: str
    software_version: str | None
    capabilities: tuple[str, ...]
    tags: tuple[str, ...]
    status: LifecycleStatus
    registered_at: datetime
    updated_at: datetime
    last_heartbeat: HeartbeatInfo | None
    connectivity: Connectivity
    health: HealthStatus
