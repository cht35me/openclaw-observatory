# SD-001 — Central and Local Observability Variants

- **Status:** Approved
- **Date:** 2026-07-19
- **Decided by:** Supervisor (Martin)
- **Context:** M001 review — proposal "Central Observatory on a VPS; observability lives outside the observed hosts"

## Decision

Design **two versions** of the Observatory:

1. **Central Observability** — runs on a VPS. This is the full, world-class
   observability platform: complete feature set, fleet-wide scope, rich UI.
2. **Local Observability** — runs on each local host. This is a minimal software
   version: lightweight, host-scoped, usable when the central Observatory is
   unreachable or not yet deployed.

## Consequences

- Architecture, schemas, and collectors must support both deployment variants.
- Storage differs per variant: ClickHouse (central) vs. SQLite (local) — see
  [SD-005](SD-005-clickhouse-central-sqlite-local.md).
- Frontend differs per variant: React SPA (central) vs. thin web UI (local) — see
  [SD-006](SD-006-react-spa-central-thin-ui-local.md).
- The original "observability lives outside the observed hosts" principle applies to
  the Central variant; the Local variant deliberately trades that for on-host
  self-sufficiency with a minimal footprint.

## Related

[architecture.md](../architecture.md) · [vision.md](../vision.md) ·
[SD-005](SD-005-clickhouse-central-sqlite-local.md) ·
[SD-006](SD-006-react-spa-central-thin-ui-local.md)
