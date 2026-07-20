# SD-014 — `/metrics` Unauthenticated, Internal Exposure Only

- **Status:** Approved
- **Date:** 2026-07-20
- **Decided by:** Supervisor (Martin)
- **Context:** M002 Gate G2 review — open question 1 in
  [backend/OPEN_QUESTIONS.md](../../backend/OPEN_QUESTIONS.md): should
  `/metrics` require a dedicated scrape token?

## Decision

**`GET /metrics` is served without authentication, but is only ever exposed on
internal networks.** Prometheus expects anonymous scraping; security comes from
the network boundary — firewall, reverse proxy, internal/tailnet networking —
not from API keys.

## Consequences

- No scrape tokens or API keys for `/metrics`; collector keys are never reused
  for read access (least privilege — collectors are write-only identities).
- The endpoint must never be reachable from the public internet. On the
  production VPS the topology is:

  ```text
  Internet → Traefik → Backend → /metrics   (restricted by network)
  ```

- Development keeps the backend bound to loopback/tailnet
  ([SD-003](SD-003-tailscale-networking.md)); deployment configuration must
  preserve the internal-only restriction.
- Metrics content remains aggregate-only: counters, latencies, versions —
  never event payloads, keys, or other secrets.

## Related

[SD-013](SD-013-health-endpoint-unauthenticated.md) ·
[SD-003](SD-003-tailscale-networking.md) ·
[backend/ARCHITECTURE.md](../../backend/ARCHITECTURE.md) ·
[security.md](../security.md)
