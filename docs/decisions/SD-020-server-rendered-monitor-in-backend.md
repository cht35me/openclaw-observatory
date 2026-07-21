# SD-020 — Observatory Monitor: Server-Rendered Page Inside the Backend

- **Status:** Proposed
- **Date:** 2026-07-21
- **Proposed by:** A001-OC01-RPSG01 (Mission M003, PR 2)
- **Context:** M003 folds the Observatory Monitor into scope (supervisor
  roadmap note): a lightweight "instrument panel" for RPSG01 showing OpenClaw
  agent health, mission progress, host CPU/RAM/storage, Docker status, and
  registered services. The React SPA (SD-006 central variant) is explicitly
  out of scope for M003, so the monitor needs a placement and exposure
  decision now.

## Decision

**The monitor is a server-rendered HTML page served by the backend itself at
`GET /monitor`, generated with the Python standard library (string
composition + `html.escape`), auto-refreshing via `<meta http-equiv=
"refresh">`. It is exposed like `/health` and `/metrics`: no API-key auth,
protected by network boundary (loopback/tailnet only, SD-003).**

Three placements were considered:

1. **Route inside the backend (chosen).** The backend already owns the
   registry read-model, mission projection, event stream, and health scoring;
   the monitor is one more *read-only view* over the same
   `RegistryService`/`MissionStorage`/`EventStorage` interfaces. Zero new
   processes, credentials, or storage clients; the page can never disagree
   with the API because it renders the same read models.
2. *Separate stdlib HTTP service.* Would need its own API key (SD-017), its
   own HTTP client, a systemd unit, and would re-fetch over HTTP what the
   backend reads natively — pure duplication at current fleet size. Rejected.
3. *Static file generator on a timer.* Stale-by-design and still needs a web
   server. Rejected.

## Rendering rationale: server-rendered HTML + 10 s polling, no JS/WebSockets

Recorded explicitly at Gate G3 review (supervisor request) so future
contributors understand this was a deliberate architectural choice, not a
shortcut. A JavaScript client with WebSocket/SSE push was considered and
rejected for this monitor:

- **Role: emergency instrument panel, not a frontend.** The monitor exists
  to answer “what is the state of this deployment *right now*?” — including
  while things are degrading. It must work from any browser (text browsers
  included), with no client state, no reconnect logic, and nothing cached
  between loads. The rich interactive UI remains the central React SPA
  (SD-006); this page deliberately does not compete with it.
- **Operational reliability.** A full-page meta refresh is self-healing by
  construction: every 10 s the browser re-requests everything, so a dropped
  connection, a backend restart, or a half-rendered page corrects itself on
  the next tick. WebSocket implementations must hand-roll reconnect,
  backoff, and staleness detection — all failure modes the monitor is
  supposed to help diagnose, not suffer from.
- **Zero JS dependencies.** No build toolchain, no npm supply chain, no
  bundler config to rot on an ARM SBC. The stdlib-only ethos matches the
  collectors (SD-019) and keeps the page auditable in one file.
- **Simplicity matches the data's cadence.** Telemetry arrives on ~30 s
  collector intervals; sub-second push would fabricate a freshness the
  data does not have. 10 s polling costs a few read-model queries per
  refresh — negligible for a single-operator loopback/tailnet page.
- **Security surface.** No JavaScript means telemetry text can never
  execute; combined with `html.escape` on every dynamic value
  (docs/security.md §9) the page renders hostile telemetry inert. A JS
  client consuming a push channel would reopen exactly that class of risk.

If a future milestone genuinely needs live push (sub-second updates,
multi-operator dashboards), that belongs to the central frontend milestone
(SD-006) and its auth layer — a superseding decision, not an edit to this
page.

## Exposure rationale

The read APIs require API keys (docs/security.md §3), but a browser page
cannot send an `X-API-Key` header without JavaScript or a login flow — both
out of scope. Following the SD-013/SD-014 precedent, the monitor is an
*operational* endpoint protected by network boundary rather than credentials:
the backend binds to `127.0.0.1` and is reachable only on-host or over the
private tailnet. The monitor renders the same information an authenticated
`GET /api/v1/fleet` returns, and telemetry-derived text is HTML-escaped at
render time (docs/security.md §9: telemetry is data, never markup).

## Consequences

- The monitor is the SD-006 "thin web UI (local)" — this decision *implements*
  the local variant, it does not touch the central React SPA plan.
- No build toolchain, no JS dependencies, no new service to babysit; the page
  costs a few read queries per refresh (10 s meta refresh).
- If the backend is down, the monitor is down too — acceptable: the backend's
  own availability is watched by systemd, `/health`, and the OBLN01
  self-heartbeat, and a monitor that outlives its data source would show
  nothing useful anyway.
- When exposure ever widens beyond the tailnet (public dashboards), the page
  inherits whatever auth layer the frontend milestone introduces (RBAC,
  architecture §2.8) — that is a new decision.
- Rendering logic lives in `backend/app/services/monitor.py` as pure
  functions (snapshot in → HTML out) and is unit-tested without a server.

## Related

[SD-003](SD-003-tailscale-networking.md) ·
[SD-006](SD-006-react-spa-central-thin-ui-local.md) ·
[SD-013](SD-013-health-endpoint-unauthenticated.md) ·
[SD-014](SD-014-metrics-endpoint-unauthenticated.md) ·
[SD-017](SD-017-api-key-bound-to-fleet-identity.md)
