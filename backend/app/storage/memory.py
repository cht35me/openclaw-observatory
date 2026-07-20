"""In-memory storage backend.

Used by the test suite as a fast, deterministic fake, and available for local
development without a database. Not for production use: data is process-local
and lost on restart.
"""

from __future__ import annotations

import asyncio

from app.models.event import Event
from app.storage.base import EventStorage, StorageError


class InMemoryEventStorage(EventStorage):
    """Stores events in a process-local list.

    ``fail`` can be toggled by tests to simulate an unreachable backend.
    """

    def __init__(self) -> None:
        self._events: list[Event] = []
        self._lock = asyncio.Lock()
        self.started = False
        #: Test hook: when True, all operations behave as if the backend is down.
        self.fail = False

    async def startup(self) -> None:
        if self.fail:
            raise StorageError("in-memory storage set to fail")
        self.started = True

    async def shutdown(self) -> None:
        self.started = False

    async def ping(self) -> bool:
        return not self.fail

    async def insert_event(self, event: Event) -> None:
        if self.fail:
            raise StorageError("in-memory storage set to fail")
        async with self._lock:
            self._events.append(event)

    async def query_events(
        self,
        collector_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        if self.fail:
            raise StorageError("in-memory storage set to fail")
        async with self._lock:
            selected = [
                event
                for event in self._events
                if (collector_id is None or event.collector_id == collector_id)
                and (event_type is None or event.event_type == event_type)
            ]
        selected.sort(key=lambda event: event.received_at, reverse=True)
        return selected[:limit]
