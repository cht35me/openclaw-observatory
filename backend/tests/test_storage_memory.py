"""Unit tests for the in-memory storage backend (the test fake itself)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.models.event import Event
from app.storage.base import StorageError
from app.storage.memory import InMemoryEventStorage


def _event(collector_id: str = "demo", event_type: str = "synthetic") -> Event:
    now = datetime.now(UTC)
    return Event(
        id=uuid4(),
        collector_id=collector_id,
        timestamp=now,
        event_type=event_type,
        payload={"n": 1},
        schema_version=1,
        received_at=now,
    )


def test_insert_and_query_filters() -> None:
    async def scenario() -> None:
        storage = InMemoryEventStorage()
        await storage.startup()
        await storage.insert_event(_event("demo", "synthetic"))
        await storage.insert_event(_event("demo", "heartbeat"))
        await storage.insert_event(_event("other", "synthetic"))

        assert len(await storage.query_events()) == 3
        assert len(await storage.query_events(collector_id="demo")) == 2
        assert len(await storage.query_events(event_type="synthetic")) == 2
        assert len(await storage.query_events(collector_id="demo", event_type="heartbeat")) == 1
        assert len(await storage.query_events(limit=2)) == 2
        assert await storage.ping() is True
        await storage.shutdown()

    asyncio.run(scenario())


def test_failure_mode_raises_storage_error() -> None:
    async def scenario() -> None:
        storage = InMemoryEventStorage()
        storage.fail = True
        assert await storage.ping() is False
        with pytest.raises(StorageError):
            await storage.insert_event(_event())

    asyncio.run(scenario())
