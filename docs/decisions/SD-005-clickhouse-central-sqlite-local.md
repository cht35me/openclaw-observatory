# SD-005 — ClickHouse for Central, SQLite for Local

- **Status:** Approved
- **Date:** 2026-07-19
- **Decided by:** Supervisor (Martin)
- **Context:** M001 review — proposal "Relational metadata store + delegated time-series
  (candidate: PostgreSQL; Prometheus at its roadmap milestone)"

## Decision

- **Central Observatory:** use a **ClickHouse** database.
- **Local Observatory:** use **SQLite**.

This supersedes the PostgreSQL candidate from the M001 proposal. The open question
"PostgreSQL-in-container vs. SQLite for MVP" is resolved by
[SD-009](SD-009-database-follows-sd-005.md), which defers to this decision.

## Consequences

- ClickHouse serves both metadata and time-series workloads centrally; its columnar
  design handles metric/event volume well beyond current fleet scale.
- Relational-integrity patterns (registry, missions, audit) must be designed with
  ClickHouse semantics in mind (append-oriented, eventual mutations) rather than
  classic OLTP assumptions.
- SQLite keeps the Local variant dependency-free and trivially embeddable.
- Time-series remain in relational tables first; Prometheus integration comes later
  ([SD-010](SD-010-relational-time-series-first.md)).

## Related

[architecture.md](../architecture.md) §2.5 ·
[SD-001](SD-001-central-and-local-observability.md) ·
[SD-009](SD-009-database-follows-sd-005.md) ·
[SD-010](SD-010-relational-time-series-first.md)
