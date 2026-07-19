"""ClickHouse storage backend (SD-005: central Observatory storage).

Uses ``clickhouse-connect`` (HTTP interface). The driver is synchronous, so
every operation runs in a worker thread via :func:`asyncio.to_thread`; an
``asyncio.Lock`` serializes access because a single driver client must not
run concurrent queries over one session.

Bootstrap (M002 "migrations/bootstrap") is idempotent DDL: it creates the
database and the ``events`` table if missing. A versioned migration framework
is deliberately deferred until a second schema change exists.

Schema notes:

* ``MergeTree`` ordered by ``(collector_id, event_type, timestamp)`` — the
  natural access path (per-collector, per-type, time-ranged), append-friendly
  per ClickHouse semantics (SD-005 consequences).
* ``payload`` is stored as a JSON-serialized ``String``; typed/materialized
  columns can be added later without breaking the canonical model.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import clickhouse_connect

from app.config import Settings
from app.models.event import Event
from app.storage.base import EventStorage, StorageError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from clickhouse_connect.driver.client import Client

#: Defense in depth: the database name comes from the environment; restrict it
#: to a safe identifier before it is interpolated into DDL/DML.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_EVENT_COLUMNS = (
    "id",
    "collector_id",
    "timestamp",
    "event_type",
    "payload",
    "schema_version",
    "received_at",
)

#: No-op latency hook used when metrics are not wired in.
def _noop_latency(operation: str, seconds: float) -> None:  # noqa: ARG001
    return None


class ClickHouseEventStorage(EventStorage):
    """Event storage backed by ClickHouse.

    ``on_db_latency`` is an optional hook (operation name, seconds) used to
    feed the ``observatory_db_latency_seconds`` metric without coupling the
    storage layer to Prometheus.
    """

    def __init__(
        self,
        settings: Settings,
        on_db_latency: Callable[[str, float], None] | None = None,
    ) -> None:
        if not _IDENTIFIER_RE.match(settings.clickhouse_database):
            raise ValueError(
                "CLICKHOUSE_DATABASE must be a plain identifier "
                "(letters, digits, underscores)."
            )
        self._settings = settings
        self._database = settings.clickhouse_database
        self._table = f"`{self._database}`.`events`"
        self._on_db_latency = on_db_latency or _noop_latency
        self._client: Client | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Connection management
    # ------------------------------------------------------------------ #

    def _connect(self) -> Client:
        """Create a driver client (runs in a worker thread).

        Connects without selecting the target database so bootstrap can create
        it; all statements use fully-qualified table names instead.
        """
        return clickhouse_connect.get_client(
            host=self._settings.clickhouse_host,
            port=self._settings.clickhouse_port,
            username=self._settings.clickhouse_username,
            password=self._settings.clickhouse_password.get_secret_value(),
            connect_timeout=self._settings.clickhouse_connect_timeout,
        )

    def _get_client(self) -> Client:
        if self._client is None:
            self._client = self._connect()
        return self._client

    async def _run(self, operation: str, func: Callable[[Client], Any]) -> Any:
        """Run one driver call in a thread, timed and serialized."""
        async with self._lock:
            loop = asyncio.get_running_loop()
            start = loop.time()
            try:
                return await asyncio.to_thread(lambda: func(self._get_client()))
            except Exception as exc:
                # Force a clean reconnect on the next call.
                self._client = None
                raise StorageError(f"ClickHouse {operation} failed") from exc
            finally:
                self._on_db_latency(operation, loop.time() - start)

    # ------------------------------------------------------------------ #
    # EventStorage interface
    # ------------------------------------------------------------------ #

    async def startup(self) -> None:
        """Connect and apply idempotent schema bootstrap."""

        def bootstrap(client: Client) -> None:
            client.command(f"CREATE DATABASE IF NOT EXISTS `{self._database}`")
            client.command(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    id UUID,
                    collector_id LowCardinality(String),
                    timestamp DateTime64(3, 'UTC'),
                    event_type LowCardinality(String),
                    payload String CODEC(ZSTD(3)),
                    schema_version UInt32,
                    received_at DateTime64(3, 'UTC')
                )
                ENGINE = MergeTree
                PARTITION BY toYYYYMM(timestamp)
                ORDER BY (collector_id, event_type, timestamp)
                """
            )

        await self._run("bootstrap", bootstrap)

    async def shutdown(self) -> None:
        """Close the client; never raises."""
        client, self._client = self._client, None
        if client is not None:
            try:
                await asyncio.to_thread(client.close)
            except Exception:  # noqa: BLE001 - shutdown must not raise
                pass

    async def ping(self) -> bool:
        try:
            return bool(await self._run("ping", lambda client: client.ping()))
        except StorageError:
            return False

    async def insert_event(self, event: Event) -> None:
        row = [
            str(event.id),
            event.collector_id,
            event.timestamp,
            event.event_type,
            json.dumps(event.payload, separators=(",", ":")),
            event.schema_version,
            event.received_at,
        ]
        await self._run(
            "insert",
            lambda client: client.insert(
                self._table, [row], column_names=list(_EVENT_COLUMNS)
            ),
        )

    async def query_events(
        self,
        collector_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        conditions: list[str] = []
        parameters: dict[str, Any] = {"limit": max(1, limit)}
        if collector_id is not None:
            conditions.append("collector_id = {collector_id:String}")
            parameters["collector_id"] = collector_id
        if event_type is not None:
            conditions.append("event_type = {event_type:String}")
            parameters["event_type"] = event_type
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = (
            f"SELECT {', '.join(_EVENT_COLUMNS)} FROM {self._table} "
            f"{where} ORDER BY received_at DESC LIMIT {{limit:UInt32}}"
        )
        result = await self._run(
            "query", lambda client: client.query(query, parameters=parameters)
        )
        return [self._row_to_event(row) for row in result.result_rows]

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _row_to_event(row: tuple[Any, ...]) -> Event:
        def as_utc(value: datetime) -> datetime:
            return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

        event_id, collector_id, timestamp, event_type, payload, schema_version, received_at = row
        return Event(
            id=event_id if isinstance(event_id, UUID) else UUID(str(event_id)),
            collector_id=collector_id,
            timestamp=as_utc(timestamp),
            event_type=event_type,
            payload=json.loads(payload),
            schema_version=int(schema_version),
            received_at=as_utc(received_at),
        )
