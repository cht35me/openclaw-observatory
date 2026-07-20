# Backend Open Questions (Mission M002) — RESOLVED

All four questions raised during M002 implementation were ruled on by the
supervisor at the Gate G2 review (2026-07-20) and recorded as decisions
SD-013…SD-017. This file is kept as the audit trail; the decision records in
[docs/decisions/](../docs/decisions/README.md) are authoritative.

## 1. `/health` and `/metrics` without API-key auth → SD-013 / SD-014 ✅

**Ruling:** both stay unauthenticated.
`/health` serves infrastructure probes (Docker, Kubernetes, Traefik,
Prometheus liveness) and returns only `200 OK`/degraded — no secrets
([SD-013](../docs/decisions/SD-013-health-endpoint-unauthenticated.md)).
`/metrics` follows the Prometheus anonymous-scrape convention and is exposed
on internal networks only; security comes from firewall / reverse proxy /
internal networking, not API keys
([SD-014](../docs/decisions/SD-014-metrics-endpoint-unauthenticated.md)).

## 2. Compose file location → SD-015 ✅

**Ruling:** keep the current compose layout during Phase 1 — no early
optimization. Restructuring (root compose orchestrating `backend/`,
`frontend/`, `collectors/`, `deployment/`) happens once those services exist
([SD-015](../docs/decisions/SD-015-compose-layout-phase1.md)).

## 3. Migration strategy → SD-016 ✅

**Ruling:** no Alembic, no Flyway, no Liquibase. Plain ordered SQL files under
[`migrations/`](migrations/), executed in filename order — simple,
transparent, easy to review
([SD-016](../docs/decisions/SD-016-plain-sql-migrations.md)).
**Implemented:** the bootstrap DDL was replaced by a migration runner with a
`schema_migrations` ledger; the initial schema is `migrations/0001_init.sql`.

## 4. API key ↔ collector binding → SD-017 ✅

**Ruling:** each API key is bound permanently to exactly one Fleet Registry
identity; a collector may never submit telemetry for another `collector_id`
([SD-017](../docs/decisions/SD-017-api-key-bound-to-fleet-identity.md)).
**Implemented:** `API_KEYS` now takes `collector_id:key` bindings, a valid key
resolves to its identity, and ingestion rejects mismatched `collector_id`
with `403` (anti-spoofing).

---

Written under Mission M002 by A001-OC01-RPSG01 · resolved at Gate G2 review.
