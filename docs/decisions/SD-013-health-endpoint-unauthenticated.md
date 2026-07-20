# SD-013 — `/health` Requires No Authentication

- **Status:** Approved
- **Date:** 2026-07-20
- **Decided by:** Supervisor (Martin)
- **Context:** M002 Gate G2 review — open question 1 in
  [backend/OPEN_QUESTIONS.md](../../backend/OPEN_QUESTIONS.md): should `/health`
  require API-key authentication given docs/security.md §3 ("no anonymous read
  access")?

## Decision

**`GET /health` is served without authentication.**

The endpoint exists for infrastructure consumers — Docker healthchecks,
Kubernetes/Traefik probes, Prometheus liveness checks — which conventionally
probe without credentials. It returns only liveness/readiness status
(`200 OK` / degraded signal), never secrets or payload data.

## Consequences

- No API keys, tokens, or credentials are ever required for `/health`.
- The endpoint must remain secret-free: status, version, uptime, and database
  connectivity only.
- Protection comes from network boundaries (loopback binding, tailnet,
  firewall, reverse proxy — see [SD-003](SD-003-tailscale-networking.md) and
  [SD-014](SD-014-metrics-endpoint-unauthenticated.md)), not from
  application-level auth.
- docs/security.md §3 is scoped accordingly: operational liveness endpoints are
  an explicit, supervisor-approved exception to "no anonymous read access".

## Related

[SD-014](SD-014-metrics-endpoint-unauthenticated.md) ·
[backend/ARCHITECTURE.md](../../backend/ARCHITECTURE.md) ·
[security.md](../security.md)
