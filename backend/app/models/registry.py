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

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Fleet IDs follow FLEET.md conventions (e.g. ``A001``, ``RPSG01``, ``OBLN01``).
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


class AssetType(StrEnum):
    """What kind of thing a registry entry identifies (FLEET.md taxonomy).

    Physical hosts and the software running on them are *different assets*:
    ``RPSG01`` is a ``node`` (the physical Raspberry Pi); the Observatory
    deployment running on it (``OBLN01``) is a ``service`` that references
    its host through :attr:`FleetAsset.host_fleet_id`.
    """

    AGENT = "agent"  # autonomous agent (A-serials, e.g. A001)
    NODE = "node"  # physical/virtual host (e.g. RPSG01, VPEU01)
    SERVICE = "service"  # software deployment (e.g. OBLN01, OBCN01)
    DEVICE = "device"  # operational hardware (e.g. a Bitaxe miner)
    SENSOR = "sensor"  # measurement endpoint (e.g. environment probe)


class DeploymentRole(StrEnum):
    """Role of a service deployment in the SD-001 two-variant architecture."""

    LOCAL = "local"  # local Observatory deployment (OBLN — Observatory Local Node)
    CENTRAL = "central"  # central Observatory deployment (OBCN — Observatory Central Node)


class LifecycleStatus(StrEnum):
    """Asset lifecycle states per FLEET.md."""

    PROVISIONED = "Provisioned"
    COMMISSIONING = "Commissioning"
    ACTIVE = "Active"
    PAUSED = "Paused"
    SUSPENDED = "Suspended"
    RETIRED = "Retired"


class Environment(StrEnum):
    """Deployment environment classification (M003.5 §3e).

    Applies to every asset (nodes, services, agents) so a mixed fleet
    (production edge nodes, a staging VPS, a development bench Pi) stays
    distinguishable in fleet-wide views. Single-node deployments simply
    carry one value everywhere — the field costs nothing until the fleet
    grows (scale-out without schema change).
    """

    PRODUCTION = "Production"
    STAGING = "Staging"
    DEVELOPMENT = "Development"
    TEST = "Test"


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
    asset_type: AssetType
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
    host_fleet_id: FleetId | None = Field(
        default=None,
        description=(
            "Fleet ID of the node this asset runs on (explicit relationship, "
            "never parsed out of the Fleet ID). Mandatory for services; "
            "recommended for agents."
        ),
    )
    deployment_role: DeploymentRole | None = Field(
        default=None,
        description="local/central Observatory role; service assets only (SD-001).",
    )
    service_version: ShortText | None = Field(
        default=None,
        description=(
            "Deployed service generation (major version, e.g. 'v1'); service "
            "assets only. Mutable attribute — upgrades update it in place "
            "and never mint a new Fleet ID (FLEET.md service identity)."
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
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description=(
            "Deployment environment classification (M003.5 §3e). Defaults to "
            "Development — promotion to Production is an explicit, seeded/"
            "administered statement, never an accident."
        ),
    )
    registered_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _service_relationships(self) -> FleetAsset:
        """Service assets must be anchored to an established host node.

        A software deployment is not a place: every ``service`` entry must
        reference the node it runs on and declare its SD-001 role. Non-service
        assets must not carry a deployment role.
        """
        if self.asset_type is AssetType.SERVICE:
            if self.host_fleet_id is None:
                raise ValueError("service assets require host_fleet_id (FLEET.md)")
            if self.deployment_role is None:
                raise ValueError("service assets require deployment_role (SD-001)")
        elif self.deployment_role is not None:
            raise ValueError("deployment_role applies to service assets only")
        return self


class HeartbeatInfo(BaseModel):
    """Latest heartbeat details for an asset (derived from the event stream).

    ``uptime_seconds`` and ``failures_total`` (M004 PR3, additive): collector
    heartbeat payloads have always carried both, but the read model dropped
    them, so the frontend could not answer "how long has this collector been
    up". Optional — older events (or foreign collectors) may omit them, and
    consumers must tolerate ``null``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp: datetime
    received_at: datetime
    software_version: str | None = None
    collector_version: str | None = None
    collector_type: str | None = None
    schema_version: int | None = None
    uptime_seconds: float | None = None
    failures_total: int | None = None


class FleetAssetView(BaseModel):
    """Read-model returned by the registry API: identity + derived telemetry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fleet_id: str
    asset_type: AssetType
    nickname: str | None
    hostname: str
    role: str
    location: str
    platform: str
    os: str
    software_version: str | None
    host_fleet_id: str | None
    deployment_role: DeploymentRole | None
    service_version: str | None
    capabilities: tuple[str, ...]
    tags: tuple[str, ...]
    status: LifecycleStatus
    environment: Environment
    registered_at: datetime
    updated_at: datetime
    last_heartbeat: HeartbeatInfo | None
    connectivity: Connectivity
    health: HealthStatus
