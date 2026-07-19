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
from app.storage.clickhouse import ClickHouseEventStorage

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
