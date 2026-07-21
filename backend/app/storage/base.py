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
from app.models.mission import MissionRecord
from app.models.registry import FleetAsset


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

    async def latest_event(self, collector_id: str, event_type: str) -> Event | None:
        """Return the most recent event of ``event_type`` for one collector.

        Default implementation on top of :meth:`query_events`; backends may
        override with a more efficient query.
        """
        events = await self.query_events(collector_id=collector_id, event_type=event_type, limit=1)
        return events[0] if events else None


class RegistryStorage(ABC):
    """Interface for Fleet Registry persistence (M003 §1).

    The registry holds *identity and lifecycle* state only — mutable, but
    low-churn (seeding, commissioning, lifecycle changes). Telemetry-derived
    fields (last heartbeat, connectivity, health) are computed from the event
    stream at read time and never stored here.

    Writes happen exclusively through backend administration paths (seeding
    at startup today); collectors have no route that reaches
    :meth:`upsert_asset` — Fleet IDs are immutable from a collector's point
    of view.
    """

    @abstractmethod
    async def startup(self) -> None:
        """Prepare the backend. Idempotent; may raise :class:`StorageError`."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Release resources. Must never raise."""

    @abstractmethod
    async def upsert_asset(self, asset: FleetAsset) -> None:
        """Insert or replace one registry entry (keyed by ``fleet_id``)."""

    @abstractmethod
    async def get_asset(self, fleet_id: str) -> FleetAsset | None:
        """Return one registry entry, or ``None`` when unknown."""

    @abstractmethod
    async def list_assets(self) -> list[FleetAsset]:
        """Return all registry entries, ordered by ``fleet_id``."""


class MissionStorage(ABC):
    """Interface for mission current-state projections (M003 §4).

    Transition history is the event stream (``mission_update`` events); this
    store keeps only the latest state per mission for fast reads.
    """

    @abstractmethod
    async def startup(self) -> None:
        """Prepare the backend. Idempotent; may raise :class:`StorageError`."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Release resources. Must never raise."""

    @abstractmethod
    async def upsert_mission(self, record: MissionRecord) -> None:
        """Insert or replace one mission record (keyed by ``mission_id``)."""

    @abstractmethod
    async def get_mission(self, mission_id: str) -> MissionRecord | None:
        """Return one mission record, or ``None`` when unknown."""

    @abstractmethod
    async def list_missions(self) -> list[MissionRecord]:
        """Return all mission records, ordered by ``mission_id``."""
