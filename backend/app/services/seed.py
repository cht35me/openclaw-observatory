"""Fleet Registry seed data and seeding routine (Mission M003 §1).

The seed entries below are derived from [FLEET.md](../../../FLEET.md) — the
specification of record for fleet identity. Seeding runs at backend startup
and is *create-only*: an entry is inserted when its ``fleet_id`` is absent,
and never overwrites an existing record, so operational lifecycle changes
survive restarts. Fleet IDs are immutable; collectors have no code path that
creates or modifies registry entries.

Identity notes:

* ``A001`` — global agent serial per FLEET.md (the full placement identity
  ``A001-OC01-RPSG01`` is descriptive metadata, not the key).
* ``RPSG01`` — host ID per the FLEET.md host scheme.
* ``OBS01`` — the Observatory backend service itself. FLEET.md defines agent
  and host IDs only; ``OBS`` is used as a service prefix pending supervisor
  confirmation (see docs/M003-open-questions.md).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from app.models.registry import FleetAsset, LifecycleStatus
from app.storage.base import RegistryStorage

_logger = logging.getLogger("observatory.registry")

#: Seed entries derived from FLEET.md (identity fields only; telemetry-derived
#: values arrive through the event stream at runtime).
SEED_ASSETS: tuple[dict, ...] = (
    {
        "fleet_id": "A001",
        "nickname": None,  # no human-assigned nickname yet (FLEET.md: optional)
        "hostname": "raspberrypi-sg01",
        "role": "Autonomous Software Engineering Agent",
        "location": "Singapore",
        "platform": "OpenClaw",
        "os": "Linux",
        "software_version": None,
        "capabilities": ("telemetry", "heartbeat", "missions"),
        "tags": ("production", "singapore", "agent"),
        "status": LifecycleStatus.ACTIVE,
    },
    {
        "fleet_id": "RPSG01",
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
    },
    {
        "fleet_id": "OBS01",
        "nickname": None,
        "hostname": "raspberrypi-sg01",  # development placement; VPS later (SD-001)
        "role": "Observatory Backend",
        "location": "Singapore",
        "platform": "FastAPI / Python",
        "os": "Linux",
        "software_version": None,
        "capabilities": ("ingestion", "registry", "missions", "heartbeat", "metrics"),
        "tags": ("production", "singapore", "critical"),
        "status": LifecycleStatus.ACTIVE,
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
        await registry.upsert_asset(asset)
        created += 1
        _logger.info("registry seeded", extra={"collector_id": fleet_id})
    return created
