# Supervisor Decisions

Architecture and technology decisions made by the fleet supervisor. Each decision is
recorded as `SD-NNN-name.md`, where `NNN` is an integer sequence and `name` is the
decision subject. Decisions are immutable once approved; a decision is changed only by
a new decision that supersedes it.

| ID | Subject | Status |
| --- | --- | --- |
| [SD-001](SD-001-central-and-local-observability.md) | Central and Local observability variants | Approved |
| [SD-002](SD-002-push-based-collectors.md) | Push-based collectors | Approved |
| [SD-003](SD-003-tailscale-networking.md) | Private networking via Tailscale | Approved |
| [SD-004](SD-004-rest-api.md) | Versioned REST/JSON API | Approved |
| [SD-005](SD-005-clickhouse-central-sqlite-local.md) | ClickHouse (central), SQLite (local) | Approved |
| [SD-006](SD-006-react-spa-central-thin-ui-local.md) | React SPA (central), thin web UI (local) | Approved |
| [SD-007](SD-007-privileged-control-required.md) | Privileged control is required | Approved |
| [SD-008](SD-008-plugin-architecture-day-one.md) | Plugin architecture from day one | Approved |
| [SD-009](SD-009-database-follows-sd-005.md) | Database for MVP → SD-005 | Approved |
| [SD-010](SD-010-relational-time-series-first.md) | Relational time-series first; Prometheus later | Approved |
| [SD-011](SD-011-python-backend.md) | Backend language: Python | Approved |
| [SD-012](SD-012-networking-follows-sd-003.md) | Tailscale vs. WireGuard → SD-003 | Approved |
| [SD-013](SD-013-health-endpoint-unauthenticated.md) | `/health` requires no authentication | Approved |
| [SD-014](SD-014-metrics-endpoint-unauthenticated.md) | `/metrics` unauthenticated, internal exposure only | Approved |
| [SD-015](SD-015-compose-layout-phase1.md) | Keep current compose layout during Phase 1 | Approved |
| [SD-016](SD-016-plain-sql-migrations.md) | Plain ordered SQL migrations, no framework | Approved |
| [SD-017](SD-017-api-key-bound-to-fleet-identity.md) | API key bound to exactly one Fleet identity | Approved |
| [SD-018](SD-018-clickhouse-versioned-row-state.md) | Mutable registry/mission state as versioned rows in ClickHouse | Accepted |
| [SD-019](SD-019-stdlib-only-collectors.md) | Collectors are standard-library-only Python | Accepted |
