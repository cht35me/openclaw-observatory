# SD-011 — Backend Language: Python

- **Status:** Approved
- **Date:** 2026-07-19
- **Decided by:** Supervisor (Martin)
- **Context:** M001 review — open question 3: "Backend language: propose at MVP gate
  (Python / TypeScript / Go candidates)?" (Recorded in the review as "SF-011";
  normalized to SD-011 in the SD-NNN sequence.)

## Decision

**Python is approved** as the backend language for the Observatory service and
first-party collectors.

## Consequences

- Framework/library selection (e.g., FastAPI vs. alternatives, ClickHouse client,
  packaging) is proposed at the Phase 1 implementation gate — libraries were not part
  of this decision.
- The React SPA ([SD-006](SD-006-react-spa-central-thin-ui-local.md)) is TypeScript/
  JavaScript territory by nature; SD-011 governs the backend and collectors.

## Related

[architecture.md](../architecture.md) · [roadmap.md](../roadmap.md) Phase 1
