# Backend Open Questions (Mission M002)

Points where M002 implementation choices touch decision records or security
policy. In each case the most conservative compliant option was implemented;
supervisor confirmation (or a follow-up SD) is requested. Per
ENGINEERING_PRINCIPLES.md §6, none of these were judged material enough to
block the mission, but all deserve an explicit ruling.

## 1. `/health` and `/metrics` are served without API-key auth

- **Tension:** [docs/security.md](../docs/security.md) §3 says "No anonymous
  read access, ever — including 'harmless' status pages." M002 requires
  operational `/health` and `/metrics` endpoints; Docker healthchecks and
  Prometheus scrapers conventionally call them without credentials.
- **What was implemented:** both endpoints respond without an API key, expose
  only service status/metric aggregates (never payload data or secrets), and
  the service itself is bound to loopback by default and intended to be
  reachable only over the tailnet (SD-003, security.md §6). OpenAPI/docs
  endpoints are disabled entirely. Reusing *collector* keys for read access
  would also violate least privilege (collectors are write-only identities).
- **Question:** should `/metrics` (and/or `/health`) require a dedicated
  scrape token in a later mission, or is tailnet-plus-loopback exposure
  sufficient?

## 2. Development compose file lives at the repository root

- **Tension:** [docs/architecture.md](../docs/architecture.md) §5 places
  deployment compose files under `infra/`; M002's acceptance criterion is
  that the system starts with plain `docker compose up`, which resolves
  `docker-compose.yml` at the invocation directory.
- **What was implemented:** the *development* stack is `docker-compose.yml`
  at the repo root (satisfies the one-command criterion). Staging/production
  compose definitions should still land in `infra/` with the deployment
  mission (roadmap), at which point the root file can move if preferred.

## 3. Bootstrap DDL instead of a migration framework

- **What was implemented:** storage startup runs idempotent
  `CREATE DATABASE/TABLE IF NOT EXISTS` DDL. A versioned migration mechanism
  (schema-version table + ordered migration steps) is deferred until a second
  schema version actually exists, to avoid speculative machinery.
- **Question:** acceptable, or should a minimal migration ledger be
  introduced before the first production deployment?

## 4. API keys are not yet bound to collector identities

- **Tension:** security.md §2 calls for per-entity, individually revocable
  credentials. `API_KEYS` supports many keys (issue one per collector, remove
  one to revoke it), but a key is not *bound* to a `collector_id` — any valid
  key may submit any `collector_id`.
- **What was implemented:** the `CollectorAuthenticator` abstraction returns
  a `CollectorPrincipal`, so a keyed mapping (`collector_id -> key`) or JWT
  subject binding can be added without changing routes.
- **Question:** should key→collector binding arrive with the first real
  collector mission, or earlier?

---

Written under Mission M002 by A001-OC01-RPSG01.
