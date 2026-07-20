# M003 Open Questions — for Gate G3 review

Judgment calls made while implementing Mission M003 that need a supervisor
ruling, following the M002 pattern
([backend/OPEN_QUESTIONS.md](../backend/OPEN_QUESTIONS.md)). Where a call is
architectural, it is additionally recorded as a **Proposed** decision in
[docs/decisions/](decisions/README.md) per the M003 supervisor guidance.

> **Confirmed, not a question:** the **Observatory Monitor** (lightweight web
> instrument panel on RPSG01) was confirmed by the supervisor as **M003
> PR 2** — a separate follow-up PR. It is intentionally *not* part of the
> M003 PR 1 branch (`a001/m003-fleet-registry-collectors`).

## 1. Fleet ID for the Observatory backend itself: `OBS01`

FLEET.md defines identity schemes for **agents** (`A001`) and **hosts**
(`RPSG01`) but not for *services*. M003 requires the registry to include the
"Observatory Backend" and the backend emits its own heartbeat, so it needs a
Fleet ID. `OBS` was used as a service prefix (`OBS01`, configurable via
`FLEET_ID`) pending a ruling.

**Needs ruling:** confirm `OBS01` (and reserve a service-prefix scheme in
FLEET.md), or assign a different convention. Fleet IDs are immutable, so a
rename before wider rollout is cheap; after it, it is not.

## 2. Mutable registry/mission state in ClickHouse → SD-018 (proposed)

ClickHouse (SD-005) is append-optimized; M003 introduces mutable state
(registry lifecycle, mission projections). Implemented as versioned rows on
`ReplacingMergeTree(revision)` with `FINAL` reads instead of introducing a
second OLTP database.

**Needs ruling:** approve
[SD-018](decisions/SD-018-clickhouse-versioned-row-state.md).

## 3. Standard-library-only collectors → SD-019 (proposed)

Collectors run on fleet hosts with zero third-party dependencies (no
virtualenv, no `pip install`, no dependency CVE surface on hosts); metrics
come from `/proc`//`/sys` and platform CLIs.

**Needs ruling:** approve
[SD-019](decisions/SD-019-stdlib-only-collectors.md).

## 4. Registry/missions API reads require a collector API key

M003 §7 asks for a *read-only* API but does not specify its authentication.
docs/security.md §3 ("no anonymous access") was applied: `GET /api/v1/fleet*`
and `GET /api/v1/missions*` require a valid collector key (any bound identity
may read; there are no read-scoped roles yet).

**Needs ruling:** is collector-key read access acceptable until RBAC arrives
(architecture §2.8), or should reads get dedicated read-only keys now?

## 5. Mission lifecycle semantics: forward-only with skips and backfill

The M003 lifecycle diagram is linear
(Created → Queued → Assigned → Running → Review → Completed). Implemented
interpretation, validated at ingestion:

- states move **forward only** (no regression, e.g. Review → Running is
  rejected as an illegal transition);
- **skipping** intermediate states is allowed (e.g. Created → Assigned), so
  coarse-grained reporters stay compatible;
- the **first report** of an unknown mission may enter at any state
  (backfill for missions that predate tracking, e.g. M001/M002);
- **repeating** the current state is allowed and refreshes metadata
  (`pr_ref`, `commit_sha`) idempotently.

Duration is computed as first-Running → Completed.

**Needs ruling:** confirm these semantics, in particular whether a
regression path (e.g. Review → Running after review findings) should ever be
legal — currently it requires a new mission report or is rejected.

## 6. Mission transitions arrive as telemetry events from collectors

Mission state changes are ingested as `mission_update` events through the
authenticated `POST /api/v1/events` pipeline (the agent collector reports
them from the agent's state file). The event stream is the durable
transition record; the backend maintains a validated current-state
projection. There is no separate write API for missions, and the backend
does not create missions on its own.

**Needs ruling:** confirm that mission tracking may remain purely
collector-reported for now (a supervisor/manual write path can be added
later without changing the model).

---

Written under Mission M003 by A001-OC01-RPSG01 · pending Gate G3 review.
