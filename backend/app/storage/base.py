"""Abstract storage interface for telemetry events.

This is the storage extension point (M002 supervisor guidance, SD-008 module
discipline): the API layer depends only on :class:`EventStorage`, so
additional backends — SQLite for the Local Observatory (SD-005), fakes for
tests — plug in without touching route or ingestion code.

All methods are ``async`` so implementations backed by synchronous drivers
(e.g. ``clickhouse-connect``) can off-load to a worker thread while the event
loop stays responsive.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.event import Event


class StorageError(Exception):
    """Raised when a storage operation fails (connection, insert, query).

    The API layer maps this to a 503 response; the original driver exception
    is chained for logs, never exposed to clients.
    """


class EventStorage(ABC):
    """Interface every event-storage backend must implement."""

    @abstractmethod
    async def startup(self) -> None:
        """Prepare the backend: connect and bootstrap schema (migrations).

        Must be idempotent. May raise :class:`StorageError`; the application
        then starts in *degraded* mode and reports it via ``/health``.
        """

    @abstractmethod
    async def shutdown(self) -> None:
        """Release connections/resources. Must never raise."""

    @abstractmethod
    async def ping(self) -> bool:
        """Return ``True`` if the backend is reachable and healthy."""

    @abstractmethod
    async def insert_event(self, event: Event) -> None:
        """Persist one canonical event. Raises :class:`StorageError` on failure."""

    @abstractmethod
    async def query_events(
        self,
        collector_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Return recent events, newest first, with optional exact-match filters.

        M002 needs only this simple read path (used by tests and future
        verification tooling); richer querying arrives with later missions.
        """
