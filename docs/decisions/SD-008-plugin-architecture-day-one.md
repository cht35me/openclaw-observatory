# SD-008 — Plugin/Module Architecture from Day One

- **Status:** Approved
- **Date:** 2026-07-19
- **Decided by:** Supervisor (Martin)
- **Context:** M001 review — proposal "Plugin/module orientation in schemas and API
  contracts from day one"

## Decision

**Approved from day one.** Each capability domain (agents, hosts, GitHub, Claude usage,
Bitaxe, future systems) is a module with its own collector(s), schemas, and dashboard
panel, registered against stable core interfaces (ingestion, storage, alerting, UI
slots).

## Consequences

- Schemas and API contracts are modular from the first line of implementation code.
- Internals may still start monolith-shaped, but module boundaries in contracts are
  binding.
- New domains onboard without core rewrites; this is the proof criterion at
  [roadmap.md](../roadmap.md) Phase 6.

## Related

[architecture.md](../architecture.md) §2.9 · [vision.md](../vision.md) ·
[SD-004](SD-004-rest-api.md)
