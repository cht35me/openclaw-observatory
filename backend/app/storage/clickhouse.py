"""ClickHouse storage backends (SD-005: central Observatory storage).

Uses ``clickhouse-connect`` (HTTP interface). The driver is synchronous, so
every operation runs in a worker thread via :func:`asyncio.to_thread`; an
``asyncio.Lock`` serializes access because a single driver client must not
run concurrent queries over one session.

Schema management (SD-016) uses plain, ordered SQL migration files from
``backend/migrations/`` (``0001_init.sql``, ``0002_...``), applied in
filename order at startup by :class:`ClickHouseEventStorage` (the first
backend started). Applied migrations are recorded in a ``schema_migrations``
ledger table, so startup is idempotent. No migration framework — per
supervisor decision.

Mutable state (Fleet Registry, mission projections) follows the versioned-row
pattern on ``ReplacingMergeTree`` (SD-018, proposed): updates insert a new
row with a monotonically increasing ``revision``; reads use ``FINAL`` so the
latest revision per key wins. This respects ClickHouse's append-oriented
semantics (SD-005 consequences) instead of fighting them with mutations.

Schema notes:

* ``events`` — ``MergeTree`` ordered by ``(collector_id, event_type,
  timestamp)``: the natural access path (per-collector, per-type,
  time-ranged), append-friendly.
* ``payload`` is stored as a JSON-serialized ``String``; typed/materialized
  columns can be added later without breaking the canonical model.
* ``fleet_registry`` / ``missions`` — ``ReplacingMergeTree(revision)`` keyed
  by their natural IDs (see migrations 0002/0003).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

import clickhouse_connect

from app.config import Settings
from app.models.event import Event
from app.models.mission import MissionRecord
from app.models.registry import FleetAsset, LifecycleStatus
from app.storage.base import EventStorage, MissionStorage, RegistryStorage, StorageError

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

_REGISTRY_COLUMNS = (
    "fleet_id",
    "nickname",
    "hostname",
    "role",
    "location",
    "platform",
    "os",
    "software_version",
    "capabilities",
    "tags",
    "status",
    "registered_at",
    "updated_at",
    "revision",
)

_MISSION_COLUMNS = (
    "mission_id",
    "title",
    "assigned_agent",
    "state",
    "created_at",
    "started_at",
    "completed_at",
    "pr_ref",
    "commit_sha",
    "updated_at",
    "revision",
)


#: No-op latency hook used when metrics are not wired in.
def _noop_latency(operation: str, seconds: float) -> None:  # noqa: ARG001
    return None


def _revision() -> int:
    """Monotonic-enough revision for ReplacingMergeTree versioned rows.

    Nanosecond wall-clock: strictly increasing for the practically relevant
    case (updates to one key are serialized through the storage lock and are
    seconds apart for registry/mission churn).
    """
    return time.time_ns()


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class _ClickHouseConnection:
    """Shared connection management for ClickHouse-backed storages.

    Each storage instance owns one driver client (the HTTP driver is cheap);
    all calls run in a worker thread, timed through ``on_db_latency`` and
    serialized by a per-instance lock.
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
        self._on_db_latency = on_db_latency or _noop_latency
        self._client: Client | None = None
        self._lock = asyncio.Lock()

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

    async def _close(self) -> None:
        """Close the client; never raises."""
        client, self._client = self._client, None
        if client is not None:
            try:
                await asyncio.to_thread(client.close)
            except Exception:  # noqa: BLE001 - shutdown must not raise
                pass

    async def _ping(self) -> bool:
        try:
            return bool(await self._run("ping", lambda client: client.ping()))
        except StorageError:
            return False


class ClickHouseEventStorage(_ClickHouseConnection, EventStorage):
    """Event storage backed by ClickHouse.

    ``on_db_latency`` is an optional hook (operation name, seconds) used to
    feed the ``observatory_db_latency_seconds`` metric without coupling the
    storage layer to Prometheus.

    This backend also owns schema bootstrap: :meth:`startup` applies pending
    SQL migrations, so it must start before the registry/mission backends.
    """

    def __init__(
        self,
        settings: Settings,
        on_db_latency: Callable[[str, float], None] | None = None,
        migrations_dir: Path | None = None,
    ) -> None:
        super().__init__(settings, on_db_latency)
        self._table = f"`{self._database}`.`events`"
        self._migrations_table = f"`{self._database}`.`schema_migrations`"
        self._migrations_dir = migrations_dir or DEFAULT_MIGRATIONS_DIR

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
        await self._close()

    async def ping(self) -> bool:
        return await self._ping()

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
        event_id, collector_id, timestamp, event_type, payload, schema_version, received_at = row
        return Event(
            id=event_id if isinstance(event_id, UUID) else UUID(str(event_id)),
            collector_id=collector_id,
            timestamp=_as_utc(timestamp),
            event_type=event_type,
            payload=json.loads(payload),
            schema_version=int(schema_version),
            received_at=_as_utc(received_at),
        )


class ClickHouseRegistryStorage(_ClickHouseConnection, RegistryStorage):
    """Fleet Registry storage on ``fleet_registry`` (ReplacingMergeTree).

    Schema is created by migration ``0002_fleet_registry.sql``, applied by
    :class:`ClickHouseEventStorage` at startup.
    """

    def __init__(
        self,
        settings: Settings,
        on_db_latency: Callable[[str, float], None] | None = None,
    ) -> None:
        super().__init__(settings, on_db_latency)
        self._table = f"`{self._database}`.`fleet_registry`"

    async def startup(self) -> None:
        if not await self._ping():
            raise StorageError("ClickHouse unreachable for registry storage")

    async def shutdown(self) -> None:
        await self._close()

    async def upsert_asset(self, asset: FleetAsset) -> None:
        row = [
            asset.fleet_id,
            asset.nickname or "",
            asset.hostname,
            asset.role,
            asset.location,
            asset.platform,
            asset.os,
            asset.software_version or "",
            list(asset.capabilities),
            list(asset.tags),
            asset.status.value,
            asset.registered_at,
            asset.updated_at,
            _revision(),
        ]
        await self._run(
            "registry_upsert",
            lambda client: client.insert(
                self._table, [row], column_names=list(_REGISTRY_COLUMNS)
            ),
        )

    async def get_asset(self, fleet_id: str) -> FleetAsset | None:
        query = (
            f"SELECT {', '.join(_REGISTRY_COLUMNS)} FROM {self._table} FINAL "
            "WHERE fleet_id = {fleet_id:String} LIMIT 1"
        )
        result = await self._run(
            "registry_get",
            lambda client: client.query(query, parameters={"fleet_id": fleet_id}),
        )
        rows = result.result_rows
        return self._row_to_asset(rows[0]) if rows else None

    async def list_assets(self) -> list[FleetAsset]:
        query = (
            f"SELECT {', '.join(_REGISTRY_COLUMNS)} FROM {self._table} FINAL "
            "ORDER BY fleet_id"
        )
        result = await self._run("registry_list", lambda client: client.query(query))
        return [self._row_to_asset(row) for row in result.result_rows]

    @staticmethod
    def _row_to_asset(row: tuple[Any, ...]) -> FleetAsset:
        (
            fleet_id,
            nickname,
            hostname,
            role,
            location,
            platform,
            os_name,
            software_version,
            capabilities,
            tags,
            status,
            registered_at,
            updated_at,
            _rev,
        ) = row
        return FleetAsset(
            fleet_id=fleet_id,
            nickname=nickname or None,
            hostname=hostname,
            role=role,
            location=location,
            platform=platform,
            os=os_name,
            software_version=software_version or None,
            capabilities=tuple(capabilities),
            tags=tuple(tags),
            status=LifecycleStatus(status),
            registered_at=_as_utc(registered_at),
            updated_at=_as_utc(updated_at),
        )


class ClickHouseMissionStorage(_ClickHouseConnection, MissionStorage):
    """Mission projection storage on ``missions`` (ReplacingMergeTree).

    Schema is created by migration ``0003_missions.sql``.
    """

    def __init__(
        self,
        settings: Settings,
        on_db_latency: Callable[[str, float], None] | None = None,
    ) -> None:
        super().__init__(settings, on_db_latency)
        self._table = f"`{self._database}`.`missions`"

    async def startup(self) -> None:
        if not await self._ping():
            raise StorageError("ClickHouse unreachable for mission storage")

    async def shutdown(self) -> None:
        await self._close()

    async def upsert_mission(self, record: MissionRecord) -> None:
        row = [
            record.mission_id,
            record.title,
            record.assigned_agent or "",
            record.state,
            record.created_at,
            record.started_at,
            record.completed_at,
            record.pr_ref or "",
            record.commit_sha or "",
            record.updated_at,
            _revision(),
        ]
        await self._run(
            "mission_upsert",
            lambda client: client.insert(
                self._table, [row], column_names=list(_MISSION_COLUMNS)
            ),
        )

    async def get_mission(self, mission_id: str) -> MissionRecord | None:
        query = (
            f"SELECT {', '.join(_MISSION_COLUMNS)} FROM {self._table} FINAL "
            "WHERE mission_id = {mission_id:String} LIMIT 1"
        )
        result = await self._run(
            "mission_get",
            lambda client: client.query(query, parameters={"mission_id": mission_id}),
        )
        rows = result.result_rows
        return self._row_to_mission(rows[0]) if rows else None

    async def list_missions(self) -> list[MissionRecord]:
        query = (
            f"SELECT {', '.join(_MISSION_COLUMNS)} FROM {self._table} FINAL "
            "ORDER BY mission_id"
        )
        result = await self._run("mission_list", lambda client: client.query(query))
        return [self._row_to_mission(row) for row in result.result_rows]

    @staticmethod
    def _row_to_mission(row: tuple[Any, ...]) -> MissionRecord:
        (
            mission_id,
            title,
            assigned_agent,
            state,
            created_at,
            started_at,
            completed_at,
            pr_ref,
            commit_sha,
            updated_at,
            _rev,
        ) = row
        return MissionRecord(
            mission_id=mission_id,
            title=title,
            assigned_agent=assigned_agent or None,
            state=state,
            created_at=_as_utc(created_at),
            started_at=_as_utc(started_at),
            completed_at=_as_utc(completed_at),
            pr_ref=pr_ref or None,
            commit_sha=commit_sha or None,
            updated_at=_as_utc(updated_at),
        )
