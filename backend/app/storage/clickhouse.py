"""ClickHouse storage backend (SD-005: central Observatory storage).

Uses ``clickhouse-connect`` (HTTP interface). The driver is synchronous, so
every operation runs in a worker thread via :func:`asyncio.to_thread`; an
``asyncio.Lock`` serializes access because a single driver client must not
run concurrent queries over one session.

Schema management (SD-016) uses plain, ordered SQL migration files from
``backend/migrations/`` (``0001_init.sql``, ``0002_...``), applied in
filename order at startup. Applied migrations are recorded in a
``schema_migrations`` ledger table, so startup is idempotent. No migration
framework (no Alembic/Flyway/Liquibase) — per supervisor decision.

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
from pathlib import Path
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

#: Ordered SQL migration files (SD-016): backend/migrations/NNNN_name.sql.
DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

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
        migrations_dir: Path | None = None,
    ) -> None:
        if not _IDENTIFIER_RE.match(settings.clickhouse_database):
            raise ValueError(
                "CLICKHOUSE_DATABASE must be a plain identifier "
                "(letters, digits, underscores)."
            )
        self._settings = settings
        self._database = settings.clickhouse_database
        self._table = f"`{self._database}`.`events`"
        self._migrations_table = f"`{self._database}`.`schema_migrations`"
        self._migrations_dir = migrations_dir or DEFAULT_MIGRATIONS_DIR
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
        """Connect and apply pending SQL migrations in filename order (SD-016)."""

        migrations = self._load_migrations()

        def bootstrap(client: Client) -> None:
            client.command(f"CREATE DATABASE IF NOT EXISTS `{self._database}`")
            client.command(
                f"""
                CREATE TABLE IF NOT EXISTS {self._migrations_table} (
                    name String,
                    applied_at DateTime64(3, 'UTC')
                )
                ENGINE = MergeTree
                ORDER BY name
                """
            )
            applied = {
                row[0]
                for row in client.query(
                    f"SELECT name FROM {self._migrations_table}"
                ).result_rows
            }
            for name, statements in migrations:
                if name in applied:
                    continue
                for statement in statements:
                    client.command(statement)
                client.insert(
                    self._migrations_table,
                    [[name, datetime.now(UTC)]],
                    column_names=["name", "applied_at"],
                )

        await self._run("bootstrap", bootstrap)

    def _load_migrations(self) -> list[tuple[str, list[str]]]:
        """Read ``NNNN_name.sql`` files, sorted, split into statements.

        The ``{database}`` token in migration SQL is replaced with the
        (identifier-validated) configured database name.
        """
        if not self._migrations_dir.is_dir():
            raise StorageError(f"migrations directory not found: {self._migrations_dir}")
        migrations: list[tuple[str, list[str]]] = []
        for path in sorted(self._migrations_dir.glob("*.sql")):
            sql = path.read_text(encoding="utf-8").replace("{database}", self._database)
            lines = [
                line for line in sql.splitlines() if not line.lstrip().startswith("--")
            ]
            statements = [
                statement.strip()
                for statement in "\n".join(lines).split(";")
                if statement.strip()
            ]
            if statements:
                migrations.append((path.name, statements))
        return migrations

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
