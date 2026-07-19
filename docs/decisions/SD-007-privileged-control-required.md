# SD-007 — Privileged Control Is Required

- **Status:** Approved
- **Date:** 2026-07-19
- **Decided by:** Supervisor (Martin)
- **Context:** M001 review — proposal "Hard boundary between monitoring (read-only) and
  privileged control (late-phase, human-gated, separately authenticated)"

## Decision

**Privileged control is a required capability**, not an optional aspiration. The
Observatory will ship a control surface (e.g., pausing an agent, approving a mission)
in addition to read-only monitoring.

The founding boundary stands: monitoring remains read-only by construction; control is
a separate, explicitly authorized surface with separate authentication, human
confirmation for privileged actions, and an append-only audit trail. Control features
remain late-phase and gated per [roadmap.md](../roadmap.md) Phase 7.

## Consequences

- Control-plane requirements move from "possible future" to committed scope.
- Schema and API design must reserve room for the control surface from the start
  (consistent with [SD-008](SD-008-plugin-architecture-day-one.md)).
- Security requirements SEC-4/SEC-5 and NFR-14 in
  [requirements.md](../requirements.md) become firm commitments.

## Related

[vision.md](../vision.md) · [architecture.md](../architecture.md) §2.8 ·
[security.md](../security.md) · [roadmap.md](../roadmap.md)
