"""Fleet Registry seed data and seeding routine (Mission M003 §1).

The seed entries below are derived from [FLEET.md](../../../FLEET.md) — the
specification of record for fleet identity. Seeding runs at backend startup
and is *create-only*: an entry is inserted when its ``fleet_id`` is absent,
and never overwrites an existing record, so operational lifecycle changes
survive restarts. Fleet IDs are immutable; collectors have no code path that
creates or modifies registry entries.

Identity notes (FLEET.md identity model):

* ``A001`` — global agent serial (``asset_type=agent``); the full placement
  identity ``A001-OC01-RPSG01`` is descriptive metadata, not the key. Its
  host relationship is explicit: ``host_fleet_id=RPSG01``.
* ``RPSG01`` — the physical Raspberry Pi host (``asset_type=node``) per the
  FLEET.md host scheme.
* ``OBLN01`` — the Observatory backend running on RPSG01: a *separate
  service asset* (``asset_type=service``), not a property of the node.
  ``OBLN`` = Observatory Local Node deployment (``OBCN`` = the future central
  deployment). Placement/version are mutable registry attributes
  (``host_fleet_id``, ``deployment_role``, ``service_version``), never
  encoded into the immutable Fleet ID.

Seed integrity: every seeded service must reference a host node that exists
(earlier in the seed tuple or already registered) — enforced at seed time.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from app.models.registry import (
    AssetType,
    DeploymentRole,
    Environment,
    FleetAsset,
    LifecycleStatus,
)
from app.storage.base import RegistryStorage

_logger = logging.getLogger("observatory.registry")

#: Seed entries derived from FLEET.md (identity fields only; telemetry-derived
#: values arrive through the event stream at runtime).
SEED_ASSETS: tuple[dict, ...] = (
    {
        "fleet_id": "RPSG01",  # nodes first: services below reference them
        "asset_type": AssetType.NODE,
        "nickname": None,
        "hostname": "raspberrypi-sg01",
        "role": "Fleet host",
        "location": "Singapore",
        "platform": "Raspberry Pi",
        "os": "Linux (Raspberry Pi OS)",
        "software_version": None,
        "capabilities": ("telemetry", "heartbeat", "docker"),
        "tags": ("production", "singapore", "edge"),
        "status": LifecycleStatus.ACTIVE,
        "environment": Environment.PRODUCTION,
    },
    {
        "fleet_id": "A001",
        "asset_type": AssetType.AGENT,
        "nickname": None,  # no human-assigned nickname yet (FLEET.md: optional)
        "hostname": "raspberrypi-sg01",
        "role": "Autonomous Software Engineering Agent",
        "location": "Singapore",
        "platform": "OpenClaw",
        "os": "Linux",
        "software_version": None,
        "host_fleet_id": "RPSG01",
        "capabilities": ("telemetry", "heartbeat", "missions"),
        "tags": ("production", "singapore", "agent"),
        "status": LifecycleStatus.ACTIVE,
        "environment": Environment.PRODUCTION,
    },
    {
        "fleet_id": "OBLN01",  # Observatory Local Node deployment 01 (FLEET.md)
        "asset_type": AssetType.SERVICE,
        "nickname": None,
        "hostname": "raspberrypi-sg01",  # development placement; central OBCN on VPS later (SD-001)
        "role": "Observatory Backend",
        "location": "Singapore",
        "platform": "FastAPI / Python",
        "os": "Linux",
        "software_version": None,
        "host_fleet_id": "RPSG01",
        "deployment_role": DeploymentRole.LOCAL,
        "service_version": "v1",
        "capabilities": ("ingestion", "registry", "missions", "heartbeat", "metrics"),
        "tags": ("production", "singapore", "critical"),
        "status": LifecycleStatus.ACTIVE,
        "environment": Environment.PRODUCTION,
    },
)


async def seed_registry(
    registry: RegistryStorage,
    now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    """Insert missing seed entries; never overwrite existing ones.

    Returns the number of entries created.
    """
    created = 0
    for entry in SEED_ASSETS:
        fleet_id = entry["fleet_id"]
        if await registry.get_asset(fleet_id) is not None:
            continue
        now = now_fn()
        asset = FleetAsset(registered_at=now, updated_at=now, **entry)
        host_id = asset.host_fleet_id
        if host_id is not None and await registry.get_asset(host_id) is None:
            raise ValueError(
                f"seed entry {fleet_id} references unknown host node {host_id}; "
                "host nodes must be established before dependent assets (FLEET.md)"
            )
        await registry.upsert_asset(asset)
        created += 1
        _logger.info("registry seeded", extra={"collector_id": fleet_id})
    return created
