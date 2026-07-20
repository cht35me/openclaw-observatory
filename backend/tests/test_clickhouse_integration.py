"""ClickHouse integration tests.

These tests require a reachable ClickHouse server (e.g. ``docker compose up
clickhouse``) and **skip automatically** when none is available, so the suite
stays green in offline development environments.

Connection details come from the standard environment variables
(``CLICKHOUSE_HOST`` etc.); the tests write to a dedicated
``observatory_test`` database to avoid touching operational data.
"""

from __future__ import annotations

import asyncio
import socket
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.config import Settings
from app.models.event import Event
from app.models.mission import MissionRecord
from app.models.registry import FleetAsset, LifecycleStatus
from app.storage.clickhouse import (
    ClickHouseEventStorage,
    ClickHouseMissionStorage,
    ClickHouseRegistryStorage,
)

_BASE = Settings(_env_file=None)
_SETTINGS = Settings(
    _env_file=None,
    clickhouse_host=_BASE.clickhouse_host,
    clickhouse_database="observatory_test",
)


def _clickhouse_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _clickhouse_reachable(_SETTINGS.clickhouse_host, _SETTINGS.clickhouse_port),
    reason="no ClickHouse server reachable; integration tests skipped",
)


def test_bootstrap_insert_query_roundtrip() -> None:
    async def scenario() -> None:
        latencies: list[str] = []
        storage = ClickHouseEventStorage(
            _SETTINGS, on_db_latency=lambda op, seconds: latencies.append(op)
        )
        await storage.startup()
        assert await storage.ping() is True

        now = datetime.now(UTC)
        event = Event(
            id=uuid4(),
            collector_id="integration-test",
            timestamp=now,
            event_type="synthetic",
            payload={"temperature": 41, "status": "ok"},
            schema_version=1,
            received_at=now,
        )
        await storage.insert_event(event)

        results = await storage.query_events(collector_id="integration-test", limit=10)
        stored = next((item for item in results if item.id == event.id), None)
        assert stored is not None, "inserted event must be queryable"
        assert stored.event_type == "synthetic"
        assert stored.payload == {"temperature": 41, "status": "ok"}
        assert stored.schema_version == 1
        assert abs((stored.timestamp - now).total_seconds()) < 0.01

        assert "bootstrap" in latencies
        assert "insert" in latencies
        assert "query" in latencies
        await storage.shutdown()

    asyncio.run(scenario())


def test_startup_is_idempotent() -> None:
    async def scenario() -> None:
        storage = ClickHouseEventStorage(_SETTINGS)
        await storage.startup()
        await storage.startup()  # bootstrap DDL must be safely re-runnable
        assert await storage.ping() is True
        await storage.shutdown()

    asyncio.run(scenario())


def test_registry_versioned_upsert_roundtrip() -> None:
    """ReplacingMergeTree + FINAL: the newest revision per fleet_id wins."""

    async def scenario() -> None:
        events = ClickHouseEventStorage(_SETTINGS)
        await events.startup()  # applies migrations 0002/0003
        registry = ClickHouseRegistryStorage(_SETTINGS)
        await registry.startup()

        now = datetime.now(UTC)
        fleet_id = f"ITEST{uuid4().hex[:8].upper()}"
        asset = FleetAsset(
            fleet_id=fleet_id,
            nickname=None,
            hostname="integration-host",
            role="Integration Test Asset",
            location="Singapore",
            platform="pytest",
            os="Linux",
            software_version=None,
            capabilities=("telemetry", "heartbeat"),
            tags=("lab",),
            status=LifecycleStatus.ACTIVE,
            registered_at=now,
            updated_at=now,
        )
        await registry.upsert_asset(asset)
        stored = await registry.get_asset(fleet_id)
        assert stored is not None
        assert stored.nickname is None
        assert stored.capabilities == ("telemetry", "heartbeat")
        assert stored.tags == ("lab",)

        # Update: new versioned row must supersede the old one under FINAL.
        updated = stored.model_copy(
            update={"nickname": "Testy", "status": LifecycleStatus.PAUSED}
        )
        await registry.upsert_asset(updated)
        stored = await registry.get_asset(fleet_id)
        assert stored.nickname == "Testy"
        assert stored.status is LifecycleStatus.PAUSED

        listing = await registry.list_assets()
        assert sum(1 for item in listing if item.fleet_id == fleet_id) == 1

        await registry.shutdown()
        await events.shutdown()

    asyncio.run(scenario())


def test_mission_versioned_upsert_roundtrip() -> None:
    async def scenario() -> None:
        events = ClickHouseEventStorage(_SETTINGS)
        await events.startup()
        missions = ClickHouseMissionStorage(_SETTINGS)
        await missions.startup()

        now = datetime.now(UTC)
        mission_id = f"M9{int(now.timestamp()) % 100000}"
        record = MissionRecord(
            mission_id=mission_id,
            title="Integration mission",
            assigned_agent="A001",
            state="Created",
            created_at=now,
            started_at=None,
            completed_at=None,
            pr_ref=None,
            commit_sha=None,
            updated_at=now,
        )
        await missions.upsert_mission(record)
        stored = await missions.get_mission(mission_id)
        assert stored is not None
        assert stored.state == "Created"
        assert stored.started_at is None

        completed = stored.model_copy(
            update={
                "state": "Completed",
                "started_at": now,
                "completed_at": now,
                "commit_sha": "abc1234",
            }
        )
        await missions.upsert_mission(completed)
        stored = await missions.get_mission(mission_id)
        assert stored.state == "Completed"
        assert stored.commit_sha == "abc1234"
        assert stored.duration_seconds == 0.0

        await missions.shutdown()
        await events.shutdown()

    asyncio.run(scenario())
