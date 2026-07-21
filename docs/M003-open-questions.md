# M003 Open Questions — Gate G3 review

Judgment calls made while implementing Mission M003, following the M002
pattern ([backend/OPEN_QUESTIONS.md](../backend/OPEN_QUESTIONS.md)). Where a
call is architectural, it is additionally recorded as a **Proposed** decision
in [docs/decisions/](decisions/README.md) per the M003 supervisor guidance.

**Status 2026-07-21:** all six questions received supervisor direction in the
pre-PR review passes; the resolutions below are implemented on the PR 1
branch. The final review passed and SD-018/SD-019 were **Accepted** by the
supervisor at the Gate G3 review.

> **PR split (supervisor-defined):**
> **PR 1** — Fleet Registry; mission persistence and projections; heartbeat
> and offline/online processing; read-only APIs; backend self-monitoring;
> schemas and storage; tests; architecture and decision documentation.
> **PR 2** (branch `a001/m003-collectors-monitor`) — deployable RPSG01
> collector utility; OpenClaw, Raspberry Pi, and Docker collectors; real
> RPSG01 installation and validation; lightweight Observatory Monitor.

## 1. Fleet ID for the Observatory backend itself — **RESOLVED: `OBLN01`**

FLEET.md originally defined identity schemes for agents (`A001`) and hosts
(`RPSG01`) but not for *services*. The interim `OBS01` placeholder is
**replaced** by the refined identity model (supervisor direction,
2026-07-20):

- New `asset_type` field: `agent | node | service | device | sensor`.
- **`RPSG01` is the physical Raspberry Pi node; the Observatory backend
  running on it is a separate `service` asset** — software and hosts are
  different asset types.
- Service Fleet IDs: `<DEPLOYMENT-TYPE><NN>` with reserved prefixes
  **`OBLN`** (Observatory Local Node deployment) and **`OBCN`** (Observatory
  Central Node deployment). The backend on RPSG01 is **`OBLN01`**.
- Placement/role/version are **explicit relationship fields**
  (`host_fleet_id=RPSG01`, `deployment_role=local`, `service_version=v1`),
  never encoded into or parsed out of the immutable Fleet ID. Re-hosting or
  upgrading updates attributes and does **not** mint a new identity; a
  genuinely new deployment (second local node, the central node) does.

Full scheme and lifecycle consequences: [FLEET.md](../FLEET.md) §“Service
Identity Scheme”. Implemented in migration 0002, seed data, models, and API.

## 2. Mutable registry/mission state in ClickHouse → SD-018 — **RESOLVED (wording final, approval at G3)**

ClickHouse (SD-005) is append-optimized; M003 introduces mutable state.
Implemented as versioned rows on `ReplacingMergeTree(revision)`.

**Merge-independence guarantee (verified in code):** all latest-row reads in
`backend/app/storage/clickhouse.py` use `SELECT … FINAL`, which collapses
row versions at query time — correctness **never depends on background
merges**; a new revision is visible on the next read. `revision` is
`time.time_ns()` with per-backend write serialization, so it is strictly
increasing per key — valid under SD-018's explicit single-writer assumption.
Details: [SD-018](decisions/SD-018-clickhouse-versioned-row-state.md)
(Status: **Accepted**, supervisor, 2026-07-21).

## 3. Standard-library-only collectors → SD-019 — **RESOLVED (wording final, approval at G3)**

Collectors run on fleet hosts with zero third-party dependencies. The
deployable collector package ships in PR 2; SD-019 governs it.
Details: [SD-019](decisions/SD-019-stdlib-only-collectors.md)
(Status: **Accepted**, supervisor, 2026-07-21).

## 4. Read-API authentication — **RESOLVED: authenticated identity reads, reconciled with SD-017**

`GET /api/v1/fleet*` and `GET /api/v1/missions*` require a valid API key
(docs/security.md §3: no anonymous access, ever). Reconciliation with
[SD-017](decisions/SD-017-api-key-bound-to-fleet-identity.md):

- SD-017's property — *every key resolves to exactly one Fleet identity* —
  holds for reads too: read access is authenticated **and attributable** to
  a fleet identity (audit logging), even though its enforcement bite is on
  the write path (no cross-identity event submission).
- Any bound identity may read the whole registry: all current identities are
  trusted fleet infrastructure, and fleet-wide visibility is the point of
  the registry. There is no read-scope mechanism yet.
- Dedicated read-only keys / RBAC arrive with the frontend milestone
  (architecture §2.8); introducing a parallel key scheme now would duplicate
  that work without a consumer.

## 5. Mission lifecycle semantics — **RESOLVED: exact transition graph defined**

Supervisor ruling (2026-07-21): **normal operation follows the explicit
lifecycle graph; forward skips are reserved for privileged
backfill/recovery; Completed is terminal.**

**Normal operation** (`backfill` absent/false) — self-loop (idempotent
metadata refresh) or exactly one step forward:

| From \ To | Created | Queued | Assigned | Running | Review | Completed |
| --- | --- | --- | --- | --- | --- | --- |
| *(unknown)* | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Created | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| Queued | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ |
| Assigned | ✗ | ✗ | ✓ | ✓ | ✗ | ✗ |
| Running | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ |
| Review | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ |
| Completed | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |

**Privileged backfill/recovery** (`backfill: true` on the `mission_update`
payload; every use is audit-logged with mission, states, and collector
identity) — may *enter at any state* for an unknown mission (import of
missions predating tracking, e.g. M001/M002) or *jump forward* over
intermediate states for a known mission (`index(new) ≥ index(current)`,
recovery after reporting gaps).

In **both** modes:

- **Regression is rejected (409).** Review findings are represented by
  staying in `Review` until rework lands — not by moving backwards. If a
  regression path is ever needed, it will be proposed as a lifecycle change,
  not silently allowed.
- **Completed is terminal** — only its metadata-refresh self-loop remains
  legal, backfill included.
- Duration = first-`Running` → `Completed`.

Implemented and documented in `backend/app/models/mission.py`
(`is_valid_transition`), enforced at ingestion in
`backend/app/services/pipeline.py`.

*PR 2 note:* a collector first observing a mission that is already mid-flight
(e.g. the agent collector syncing an in-progress mission) must submit that
initial observation with `backfill: true`; subsequent observations follow the
normal one-step graph.

## 6. Mission records via collector telemetry — **RESOLVED: observed state only, never canonical**

Confirmed model: **collectors may report *observed* mission state but cannot
authoritatively create or mutate canonical mission records.**

- Mission state changes arrive as `mission_update` events through the
  authenticated `POST /api/v1/events` pipeline; the event stream is the
  durable, auditable transition record.
- The backend's `missions` table is a **validated projection** of that
  observed stream (transition rules above), not a canonical registry; the
  canonical mission definition remains the supervisor's mission documents.
- This mirrors the registry rule (collectors can never create or modify
  fleet *identities* — enforced: heartbeats for unknown Fleet IDs are
  rejected 403); the difference is that mission *observations* are accepted
  and projected, while identity is seeded/administered only.
- A supervisor/manual write path can be added later without changing the
  model.

---

## PR 2 — collectors, RPSG01 deployment, Observatory Monitor

Judgment calls made while implementing PR 2 (branch
`a001/m003-collectors-monitor`), 2026-07-21:

### 7. First sync of an in-flight mission ⇒ collector stamps `backfill: true`

Implements the PR 2 note under question 5: when the agent collector observes
a mission for the first time (per collector process) in any state other than
`Created`, it stamps `backfill: true` on that initial `mission_update` — the
backend only admits entry at a non-initial state as a privileged, audit-logged
backfill transition. Subsequent observations follow the normal one-step graph
and carry no flag (unless the agent state file sets it explicitly for an
operator-driven recovery jump, which is passed through untouched). A collector
*restart* therefore re-syncs current mission states as backfill self-loops —
idempotent, legal, and audit-visible by design. Verified live: M003 entered
the projection at `Running` with `"backfill": true` stored on the event.

### 8. Monitor placement and exposure → SD-020 (Accepted at Gate G3 review)

The Observatory Monitor is a server-rendered HTML page at `GET /monitor`
*inside the backend* (stdlib rendering + `html.escape`, meta-refresh, no
JS/build toolchain), exposed like `/health`//`/metrics`: no API key,
network-boundary protection (loopback/tailnet only). Alternatives (separate
stdlib service, static generator), the exposure rationale, and the explicit
rendering rationale (server-rendered 10 s polling vs. a JS/WebSocket client
— documented at Gate G3 review) are recorded in
[SD-020](decisions/SD-020-server-rendered-monitor-in-backend.md).

The monitor header identifies the running deployment (Gate G3 review
request): Observatory version, git commit of the running checkout (read
stdlib-only from `.git`, overridable via `GIT_COMMIT` for non-checkout
deployments; `unknown` when neither exists), and the active mission
(agent-reported, falling back to the backend's mission projection).

### 9. Token usage on the monitor — placeholder shown, future ownership ruled

M003 asks for “token usage where available.” The OpenClaw runtime does not
expose token consumption in any machine-readable file the agent collector may
read cheaply (session logs are internal, and scraping them would couple the
collector to runtime internals). The monitor shows an explicit
“n/a — not yet collected” placeholder for M003.

**Intended future ownership** (documented at Gate G3 review so the
architectural responsibility is clear):

- **Primary source: the OpenClaw runtime.** Token usage is a property of
  the agent's own execution, so the runtime is the authority. The intended
  path is a machine-readable usage field in the agent state file
  (`~/.config/observatory/agent-state.json`, §10) — or a local runtime
  usage API if one appears — maintained by the runtime/agent workflow, not
  scraped from internal session logs.
- **Transport: the existing agent collector.** It already owns the agent
  state file and reports through the authenticated push path (SD-002,
  SD-017); token usage becomes one more field on `agent_status`. No new
  collector, credentials, or service is planned for the *local* metric.
- **Claude API accounting is a cross-check, not the local source.** Provider
  billing/usage APIs are account-wide, delayed, and need provider
  credentials that do not belong on fleet nodes. If billing-grade
  reconciliation is ever wanted, it lands in the *central* Observatory as
  part of the AI-usage collector milestone (roadmap) — a separate,
  central-side concern.

The placeholder is removed when the runtime-maintained field exists; the
monitor and backend need no structural change (the `agent_status` payload is
schema-flexible).

### 10. RPSG01 deployment specifics (real installation, supervisor-authorized)

- **ClickHouse runs natively** under a systemd *user* unit
  (`deploy/systemd/observatory-clickhouse.service`): the Pi 4 (ARMv8.0)
  cannot run official CH docker images (backend/ARCHITECTURE.md). Loopback
  only; `MemoryMax=2G` guards the Pi's 4 GiB RAM.
- **ClickHouse uses the `default` user with no password** on this
  development host: the server is loopback-bound on a single-user machine,
  and the native binary's embedded config has no users.xml management.
  Acceptable for the SD-001 *local* variant only; the VPS compose stack keeps
  the passworded `observatory` user. Recorded here rather than as an SD —
  configuration, not architecture.
- **Secrets** live in untracked `~/.config/observatory/*.env` files
  (chmod 600), generated with `openssl rand -hex 32`, bound per SD-017
  (`RPSG01` → host collector, `A001` → agent collector). The repository
  carries placeholder examples only.
- **Agent state file** (`~/.config/observatory/agent-state.json`) is
  maintained by the agent (A001) as part of its working practice; the
  collector only ever reads it. Keeping it current is now part of the
  mission workflow.
- systemd sandboxing (`ProtectHome=read-only`, `ProtectSystem=strict`,
  `PrivateTmp`) worked as-written for the user units on this host (systemd
  257, unprivileged user namespaces available); no weakening was needed.

---

Written under Mission M003 by A001-OC01-RPSG01 · PR 1 resolutions implemented
2026-07-20 and accepted at Gate G3 review; PR 2 sections added 2026-07-21.
