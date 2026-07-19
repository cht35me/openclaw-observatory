# SD-002 — Push-Based Collectors

- **Status:** Approved
- **Date:** 2026-07-19
- **Decided by:** Supervisor (Martin)
- **Context:** M001 review — proposal "Push-based collectors (hosts dial out; no inbound
  access into fleet hosts) + centralized pollers for GitHub/Claude usage/Bitaxe"

## Decision

Push-based collectors are **approved**: fleet hosts dial out to the Observatory; the
Observatory needs no inbound access into any fleet host. Centralized pollers handle
external/pull-only sources (GitHub, Claude usage, Bitaxe).

## Consequences

- Collector credentials live on each host and must be individually revocable.
- Offline detection is heartbeat-absence based.
- Poller credentials are held centrally, least-privilege, and audited.

## Related

[architecture.md](../architecture.md) §2.2 · [security.md](../security.md)
