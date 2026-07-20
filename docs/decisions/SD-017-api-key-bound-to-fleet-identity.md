# SD-017 — Each API Key Is Bound to Exactly One Fleet Identity

- **Status:** Approved
- **Date:** 2026-07-20
- **Decided by:** Supervisor (Martin)
- **Context:** M002 Gate G2 review — open question 4 in
  [backend/OPEN_QUESTIONS.md](../../backend/OPEN_QUESTIONS.md): M002's
  `API_KEYS` accepted a flat key list, so any valid key could submit events
  for any `collector_id` (spoofing risk).

## Decision

**Bind each API key permanently to a single Fleet Registry identity.**
Collectors must not be allowed to submit telemetry for arbitrary
`collector_id` values.

```text
API key → Collector → Fleet Registry → collector_id
```

Not allowed: authenticating with key A while claiming `collector_id=B`.

## Consequences

- Authentication yields an identity, not just access: a valid key resolves to
  exactly one `collector_id`, and ingestion rejects any event whose
  `collector_id` does not match the authenticated identity.
- Key issuance is per entity, e.g.:

  ```text
  Singapore Pi → key → RPSG01
  Bitaxe-01    → key → BITAXE01
  Agent        → key → A001
  ```

- Revoking a key revokes exactly one identity (least privilege, individual
  revocability — security.md §2).
- This prevents collector spoofing and gives every stored event a trustworthy
  provenance — a much stronger architecture for the Fleet Registry.
- A future JWT scheme must preserve the same property (subject = one Fleet
  identity).

## Related

[FLEET.md](../../FLEET.md) · [security.md](../security.md) ·
[backend/ARCHITECTURE.md](../../backend/ARCHITECTURE.md)
