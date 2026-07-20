# SD-018 — Mutable Registry/Mission State as Versioned Rows in ClickHouse

- **Status:** Proposed
- **Date:** 2026-07-20
- **Proposed by:** A001-OC01-RPSG01 (Mission M003)
- **Context:** M003 introduces the first *mutable* state in the Observatory:
  Fleet Registry identities (lifecycle status, tags, nicknames can change)
  and mission current-state projections (state advances through the
  lifecycle). SD-005 selected ClickHouse as the only central store, but
  ClickHouse is append-optimized — row `UPDATE`s are heavyweight asynchronous
  mutations, not an OLTP primitive. A storage approach for mutable state was
  needed; per M003 supervisor guidance, it is recorded here as a proposed
  decision instead of an undocumented change.

## Decision (proposed)

**Mutable current-state lives in ClickHouse as versioned rows on
`ReplacingMergeTree(revision)` tables; every update inserts a new row with a
monotonically increasing `revision`, and reads use `FINAL` so the latest
revision per key wins.** No second database is introduced.

```text
fleet_registry   ENGINE = ReplacingMergeTree(revision) ORDER BY fleet_id
missions         ENGINE = ReplacingMergeTree(revision) ORDER BY mission_id
```

Append-only history (telemetry events, heartbeats, mission *transitions*)
continues to live in the plain `MergeTree` event stream — the event remains
the durable record; the versioned-row tables are current-state projections.

## Alternatives considered

| Alternative | Why not |
| --- | --- |
| `ALTER TABLE … UPDATE` mutations | Asynchronous, heavyweight background rewrites; not designed for frequent small updates; awkward to test. |
| Separate OLTP store (SQLite/Postgres) for registry/missions | New operational dependency and backup surface, contradicts SD-005's single central store; state volume (dozens of assets, hundreds of missions) does not justify it. |
| Keep state only in memory, rebuild from event stream at startup | Replay cost grows unboundedly with event history; projections would need snapshotting anyway — versioned rows *are* that snapshot. |

## Consequences

- Updates are cheap inserts; ClickHouse compacts old revisions in the
  background. `FINAL` on reads is acceptable at fleet scale (tiny tables).
- Every state change is still visible as an event in the event stream;
  the projection tables can be rebuilt from events if ever needed.
- If registry/mission cardinality or read patterns ever outgrow this (e.g.
  thousands of assets with high-frequency updates), a superseding decision
  can move projections to an OLTP store without touching the event model.

## Related

[SD-005](SD-005-clickhouse-central-sqlite-local.md) ·
[SD-016](SD-016-plain-sql-migrations.md) ·
[backend/migrations/0002_fleet_registry.sql](../../backend/migrations/0002_fleet_registry.sql) ·
[backend/migrations/0003_missions.sql](../../backend/migrations/0003_missions.sql)
