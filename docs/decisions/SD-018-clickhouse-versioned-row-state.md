# SD-018 — Mutable Registry/Mission State as Versioned Rows in ClickHouse

- **Status:** Proposed (final wording for Gate G3 approval)
- **Date:** 2026-07-20
- **Proposed by:** A001-OC01-RPSG01 (Mission M003)
- **Context:** M003 introduces the first *mutable* state in the Observatory:
  Fleet Registry identities (lifecycle status, tags, nicknames, host
  relationships can change) and mission current-state projections (state
  advances through the lifecycle). SD-005 selected ClickHouse as the only
  central store, but ClickHouse is append-optimized — row `UPDATE`s are
  heavyweight asynchronous mutations, not an OLTP primitive. A storage
  approach for mutable state was needed; per M003 supervisor guidance, it is
  recorded here as a proposed decision instead of an undocumented change.

## Decision

**Mutable current-state lives in ClickHouse as versioned rows on
`ReplacingMergeTree(revision)` tables. Every update inserts a new row with a
monotonically increasing `revision`; every read uses the `FINAL` modifier, so
the highest revision per key wins at query time.** No second database is
introduced.

```text
fleet_registry   ENGINE = ReplacingMergeTree(revision) ORDER BY fleet_id
missions         ENGINE = ReplacingMergeTree(revision) ORDER BY mission_id
```

Append-only history (telemetry events, heartbeats, mission *transitions*)
continues to live in the plain `MergeTree` event stream — the event remains
the durable record; the versioned-row tables are current-state projections
that can be rebuilt from events if ever needed.

## Correctness guarantee — no dependence on background merges

ReplacingMergeTree deduplicates *eventually* during background merges, which
run at ClickHouse's discretion. The Observatory **never relies on that**:

- **Every** latest-row query in
  [`backend/app/storage/clickhouse.py`](../../backend/app/storage/clickhouse.py)
  (`get_asset`, `list_assets`, `get_mission`, `list_missions`) reads with
  `SELECT … FROM <table> FINAL`, which performs merge-on-read: unmerged row
  versions are collapsed at query time and the row with the highest
  `revision` per key is returned **regardless of background-merge progress**.
  A freshly inserted update is visible on the very next read.
- `revision` is strictly increasing per key: it is nanosecond wall-clock
  (`time.time_ns()`), and all writes to one key are serialized through the
  storage backend's asyncio lock; registry/mission churn is orders of
  magnitude slower than nanosecond resolution.
- `FINAL`'s cost is proportional to unmerged parts of tiny tables (tens of
  assets, hundreds of missions) — negligible at fleet scale.

## Alternatives considered

| Alternative | Why not |
| --- | --- |
| `ALTER TABLE … UPDATE` mutations | Asynchronous, heavyweight background rewrites; not designed for frequent small updates; awkward to test. |
| Separate OLTP store (SQLite/Postgres) for registry/missions | New operational dependency and backup surface, contradicts SD-005's single central store; state volume does not justify it. |
| Keep state only in memory, rebuild from event stream at startup | Replay cost grows unboundedly with event history; projections would need snapshotting anyway — versioned rows *are* that snapshot. |
| `argMax()` aggregation instead of `FINAL` | Equivalent correctness; `FINAL` keeps queries plain `SELECT`s and the row-to-model mapping trivial. May be revisited as a pure optimization without changing this decision. |

## Consequences

- Updates are cheap inserts; ClickHouse compacts old revisions in the
  background purely as a storage optimization, never as a correctness
  requirement.
- Every state change is still visible as an event in the event stream; the
  projection tables can be rebuilt from events.
- If registry/mission cardinality or read patterns ever outgrow this (e.g.
  thousands of assets with high-frequency updates), a superseding decision
  can move projections to an OLTP store without touching the event model.

## Related

[SD-005](SD-005-clickhouse-central-sqlite-local.md) ·
[SD-016](SD-016-plain-sql-migrations.md) ·
[backend/migrations/0002_fleet_registry.sql](../../backend/migrations/0002_fleet_registry.sql) ·
[backend/migrations/0003_missions.sql](../../backend/migrations/0003_missions.sql)
