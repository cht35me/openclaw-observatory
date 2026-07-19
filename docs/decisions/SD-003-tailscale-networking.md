# SD-003 — Private Networking via Tailscale

- **Status:** Approved
- **Date:** 2026-07-19
- **Decided by:** Supervisor (Martin)
- **Context:** M001 review — proposal "Private networking via Tailscale (alternatives:
  plain WireGuard, mTLS over HTTPS)"

## Decision

**Tailscale is approved** as the private-network layer between fleet hosts and the
central Observatory. The open question "Tailscale vs. plain WireGuard" is resolved the
same way by [SD-012](SD-012-networking-follows-sd-003.md).

## Consequences

- No Observatory ports exposed to the public internet; tailnet-only exposure.
- Tailnet credentials are treated as sensitive assets.
- Headscale (self-hosted control plane) remains a future option if third-party
  dependency becomes a concern.

## Related

[architecture.md](../architecture.md) §2.3 · [security.md](../security.md) ·
[deployment.md](../deployment.md) · [SD-012](SD-012-networking-follows-sd-003.md)
