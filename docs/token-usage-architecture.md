# Token Usage Architecture (Mission M003.5 §5)

Architectural ownership of token accounting for the OpenClaw fleet.
**Documentation only — no implementation in M003.5.** This replaces the bare
"n/a — not yet collected" monitor placeholder with a ruled design; the
supervisor ruling was recorded at the Gate G3 review
([docs/M003-open-questions.md §9](M003-open-questions.md)) and is elaborated
here as the specification of record.

## 1. Intended data source: the OpenClaw runtime

Token usage is a property of the **agent's own execution**, so the OpenClaw
runtime is the authority. The intended path is a machine-readable usage
field in the agent state file (`~/.config/observatory/agent-state.json`,
maintained by the agent/runtime workflow — M003 §10), or a local runtime
usage API if one becomes available.

What the source is **not**:

- **Not session-log scraping.** OpenClaw session logs are runtime internals;
  parsing them would couple the collector to undocumented formats that can
  change with any runtime release.
- **Not provider billing APIs on fleet nodes.** Account-wide, delayed, and
  requiring provider credentials that do not belong on edge hosts.

Proposed state-file shape (advisory; the `agent_status` payload is
schema-flexible, so field additions need no backend release):

```json
{
  "token_usage": {
    "session_input_tokens": 123456,
    "session_output_tokens": 23456,
    "session_cost_usd": 1.23,
    "window_started_at": "2026-07-21T00:00:00Z",
    "source": "openclaw-runtime"
  }
}
```

## 2. Responsible transport: the agent collector

The existing **OpenClaw agent collector** (`observatory_collectors.
openclaw_agent`) already owns the agent state file and reports through the
authenticated push path (SD-002 push collectors, SD-017 key↔identity
binding). Token usage becomes **one more field on the `agent_status`
event** — no new collector, credentials, service, or event type for the
local metric. The monitor's "Token usage" line renders the field the moment
it appears; backend and monitor need no structural change.

## 3. Claude API accounting: central-side cross-check only

Provider usage/billing APIs remain a **cross-check, not the local source**.
If billing-grade reconciliation is wanted, it lands in the *central*
Observatory as part of the Claude/API usage milestone ([roadmap](roadmap.md)
Phase 3 item 2, “Claude/API usage”): a central poller with provider
credentials that never leave the central node, comparing runtime-reported
totals against account-level accounting.

## 4. Future integration approach

1. **Runtime emits usage** into the agent state file (agent workflow change
   or runtime feature — outside Observatory scope, tracked as the
   prerequisite).
2. **Agent collector forwards** `token_usage` inside `agent_status`
   (one-line change; payload is already schema-flexible).
3. **Monitor renders** the reported numbers in the OpenClaw Agent section,
   replacing the pointer text.
4. **Central milestone** adds provider-side accounting as a cross-check and
   cost dashboards (roadmap Phase 3; out of scope for the local deployment).

Until step 1 exists, the monitor deliberately shows
`n/a — runtime-owned, agent collector transport (see docs)` rather than
inventing numbers.

---

Written under Mission M003.5 by A001-OC01-RPSG01 (2026-07-21), elaborating
the Gate G3 supervisor ruling in
[M003-open-questions.md §9](M003-open-questions.md).
