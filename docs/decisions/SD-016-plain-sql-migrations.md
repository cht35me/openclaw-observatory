# SD-016 — Plain Ordered SQL Migrations, No Migration Framework

- **Status:** Approved
- **Date:** 2026-07-20
- **Decided by:** Supervisor (Martin)
- **Context:** M002 Gate G2 review — open question 3 in
  [backend/OPEN_QUESTIONS.md](../../backend/OPEN_QUESTIONS.md): M002 shipped
  idempotent bootstrap DDL; should a migration mechanism be introduced, and if
  so which?

## Decision

**ClickHouse schema evolution uses plain, ordered SQL migration files under
`backend/migrations/` — executed in filename order.** No Alembic, no Flyway,
no Liquibase.

```text
backend/
  migrations/
    0001_init.sql
    0002_events.sql
    0003_registry.sql
```

Simple, transparent, easy to review — a perfect fit for the Observatory.

## Consequences

- Every schema change is a new `NNNN_name.sql` file; existing migration files
  are immutable once merged.
- The backend applies pending migrations in order at startup and records
  applied migrations, so execution is idempotent.
- Migration SQL is reviewed like any other code — plain text in the PR, no
  framework DSL or generated diffs.
- No heavyweight migration framework is ever introduced without a superseding
  decision.

## Related

[SD-005](SD-005-clickhouse-central-sqlite-local.md) ·
[backend/ARCHITECTURE.md](../../backend/ARCHITECTURE.md)
