# SD-004 — Versioned REST/JSON API

- **Status:** Approved
- **Date:** 2026-07-19
- **Decided by:** Supervisor (Martin)
- **Context:** M001 review — proposal "Versioned REST/JSON API (/api/v1/) with shared
  schemas"

## Decision

The **REST API is approved**: JSON over HTTP with URL-prefix versioning (`/api/v1/...`),
shared schemas as the single source of truth, additive changes within a version, and
breaking changes only via a new version.

## Consequences

- Contract validation at ingestion is mandatory (REST is weakly typed without it).
- Collectors send identity and schema version with every payload.
- Both Central and Local variants ([SD-001](SD-001-central-and-local-observability.md))
  speak the same API contracts.

## Related

[architecture.md](../architecture.md) §2.4 ·
[SD-008](SD-008-plugin-architecture-day-one.md)
