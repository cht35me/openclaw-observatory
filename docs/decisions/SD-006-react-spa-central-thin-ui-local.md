# SD-006 — React SPA for Central, Thin Web UI for Local

- **Status:** Approved
- **Date:** 2026-07-19
- **Decided by:** Supervisor (Martin)
- **Context:** M001 review — proposal "Thin server-rendered dashboard for MVP; Grafana
  as complement, not replacement"

## Decision

- **Central Observatory:** develop a **full SPA using React**.
- **Local Observatory:** use a **thin web UI** (minimal, server-rendered).

This supersedes the "server-rendered pages for MVP" recommendation for the Central
variant. Grafana remains a complement for metric charts, not the primary UI.

## Consequences

- The Central frontend gains build tooling and supply-chain surface (React ecosystem);
  dependency auditing per [security.md](../security.md) applies.
- Frontend and backend separate cleanly: the React SPA consumes the versioned REST API
  ([SD-004](SD-004-rest-api.md)), which keeps API contracts honest.
- The Local variant stays minimal by design, matching
  [SD-001](SD-001-central-and-local-observability.md).

## Related

[architecture.md](../architecture.md) §2.7 · [roadmap.md](../roadmap.md) Phase 3 ·
[SD-001](SD-001-central-and-local-observability.md)
