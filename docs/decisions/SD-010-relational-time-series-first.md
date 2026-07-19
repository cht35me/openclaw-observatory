# SD-010 — Time-Series: Relational Tables First, Prometheus Later

- **Status:** Approved
- **Date:** 2026-07-19
- **Decided by:** Supervisor (Martin)
- **Context:** M001 review — open question 2: "Time-series: relational tables first
  (recommended) vs. Prometheus from the start?"

## Decision

**Relational tables first.** Numeric host metrics start in database tables
(ClickHouse centrally, SQLite locally, per
[SD-005](SD-005-clickhouse-central-sqlite-local.md)). **Prometheus integration comes
later**, at its roadmap milestone ([roadmap.md](../roadmap.md) Phase 5), revisited with
real data volumes.

## Consequences

- No Prometheus deployment during the MVP phases.
- `/metrics` (Prometheus-compatible exposure) remains planned per FR-21.
- Retention/downsampling handled with in-database jobs until Prometheus arrives.

## Related

[architecture.md](../architecture.md) §2.5 · [roadmap.md](../roadmap.md) Phase 5 ·
[SD-005](SD-005-clickhouse-central-sqlite-local.md)
