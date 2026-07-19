# Roadmap — Staged Development Milestones

This roadmap uses **dependencies and review gates**, not calendar promises. Each phase
ends with a human review gate; later phases may be re-ordered or re-scoped at any gate.
Every implementation phase is delivered as one or more missions
([MISSION.md](../MISSION.md)) with small, reviewable Pull Requests.

```text
Phase 0 ──▶ Gate G1 ──▶ Phase 1 ──▶ Phase 2 ──▶ Phase 3 ──▶ Phase 4 ──▶ Phase 5 ──▶ ...
(M001)     (arch          core       collectors   visibility   deploy     integrate
            approval)     backend    + registry   + frontend               + expand
```

## Phase 0 — Documentation and Governance Foundation (M001) ✔ this mission

**Deliverables:** vision, requirements, architecture proposal, roadmap, security and
deployment strategy, fleet identity model, agent governance, engineering principles.
**Dependencies:** none.

### Gate G1 — MVP Architecture Approval

Supervisor reviews the M001 PR and the open questions in
[architecture.md](architecture.md) (database, time-series approach, backend language,
networking). Implementation may begin only after this gate.

**Status: supervisor review received (2026-07-19).** Decisions SD-001…SD-012 are
recorded in [docs/decisions/](decisions/README.md): two Observatory variants
(central + local, SD-001), push collectors (SD-002), Tailscale (SD-003/SD-012),
versioned REST API (SD-004), ClickHouse central / SQLite local (SD-005/SD-009),
React SPA central / thin UI local (SD-006), privileged control required (SD-007),
plugin architecture from day one (SD-008), relational time-series first with
Prometheus later (SD-010), and Python backend (SD-011). The gate closes when the
M001 PR is approved and merged by the supervisor.

## Phase 1 — Core Observatory Backend

**Scope:** minimal service skeleton on the decided stack (**Python** backend per
[SD-011](decisions/SD-011-python-backend.md), **ClickHouse** storage per
[SD-005](decisions/SD-005-clickhouse-central-sqlite-local.md)): versioned REST
ingestion API, authentication for collectors, storage layer, event model, structured
logging, health endpoint, self-metrics. No UI yet beyond raw API.
**Dependencies:** G1.
**Gate:** code review + demonstrated ingestion of a synthetic payload; security checklist
from [security.md](security.md) applied.

## Phase 2 — First Collectors and Fleet Registry

Ordered within phase:

1. **Fleet Registry** (backend model + seeded A001 entry from [FLEET.md](../FLEET.md))
   — everything else references identities.
2. **Raspberry Pi collector** (CPU, RAM, disk, temperature, uptime, heartbeat) running
   on RPSG01.
3. **OpenClaw agent collector** (agent status, mission state, heartbeat, Claude Code
   status, model/runtime version).
4. **Mission tracking** (mission records and state transitions per
   [MISSION.md](../MISSION.md)).

**Dependencies:** Phase 1.
**Gate:** real telemetry from RPSG01 visible via API; registry is source of truth for
identity; offline detection demonstrated.

## Phase 3 — Engineering and Cost Visibility + Initial Frontend

1. **GitHub integration** (poller: repos, branches, latest commit, active PRs, review
   status).
2. **Claude/API usage** (tokens, estimated cost per agent).
3. **Initial frontend dashboard** (fleet overview: agents, hosts, missions, PRs, alerts;
   **React SPA** for the Central Observatory per
   [SD-006](decisions/SD-006-react-spa-central-thin-ui-local.md); may start with a
   minimal feature set and grow, but on the SPA stack from the start).
4. **Dashboard authentication** (supervisor login).

**Dependencies:** Phase 2 (registry + mission data to display).
**Gate:** supervisor can answer "what is the fleet doing right now?" from the dashboard
alone.

## Phase 4 — Production Deployment

1. **VPS staging deployment** (containerized, tailnet-only exposure, secrets management,
   backups configured) per [deployment.md](deployment.md).
2. **Production deployment on VPS** after staging soak and review.
3. **Monitoring and rollback** procedures exercised (not just written).

**Dependencies:** Phase 3 (something worth deploying).
**Gate:** production checklist in [deployment.md](deployment.md) satisfied; restore from
backup demonstrated once.

## Phase 5 — Ecosystem Integration

1. **Prometheus integration** (`/metrics` exposure; Prometheus deployment decision from
   G1 revisited with real data volumes).
2. **Grafana interoperability** (charts over Observatory/Prometheus data).
3. **Alerting maturation** (rules, severities, dedup/rate limits, quiet hours;
   Alertmanager evaluation).

**Dependencies:** Phase 4 (stable production target).
**Gate:** at least one real alert path proven end-to-end (host offline → Telegram).

## Phase 6 — Fleet and Capability Expansion

1. **Bitaxe integration** (miner status collector + dashboard module — first proof of
   the plugin model).
2. **Local Observability variant** (minimal on-host Observatory: SQLite storage, thin
   web UI, shared schemas — per
   [SD-001](decisions/SD-001-central-and-local-observability.md); may be pulled
   earlier at a gate if operational need arises).
3. **Multi-agent expansion** (A002+; possibly a second framework prefix per
   [FLEET.md](../FLEET.md); mission queue visibility).
4. **Additional hosts/platforms** (VPS collectors beyond the Observatory host,
   workstations).

**Dependencies:** Phase 5 stability; commissioning process from [FLEET.md](../FLEET.md).
**Gate:** two agents visible and distinguishable end-to-end; plugin module added without
core changes.

## Phase 7 — Hardening and Reliability

**Scope:** security review against [security.md](security.md) threat model; dependency
audit; backup/restore drills; collector-side buffering; retention/downsampling; audit
trail completeness; incident-response runbook exercised; consideration of the (still
human-gated) control-plane features from [vision.md](vision.md).
**Dependencies:** everything above — hardening never blocks earlier learning phases, but
**no control-plane capability ships before this phase completes.**
**Gate:** supervisor sign-off on hardening review.

## Continuous (all phases)

- Documentation updated in the same PR that changes behavior.
- Small PRs, human approval before merge, no direct commits to `main`.
- Security checklist applied to every phase, not only Phase 7.
- Roadmap itself re-reviewed at every gate; this document is expected to change.

## Explicitly Unscheduled

No dates are attached to any phase. Sequencing above encodes dependency order and review
gates; delivery timing depends on supervision availability, mission cadence, and review
outcomes. Promising dates without that information would violate
[ENGINEERING_PRINCIPLES.md](../ENGINEERING_PRINCIPLES.md) §15 (clear failure reporting
begins with honest planning).

---

Related: [vision.md](vision.md) · [requirements.md](requirements.md) ·
[architecture.md](architecture.md) · [security.md](security.md) ·
[deployment.md](deployment.md)
