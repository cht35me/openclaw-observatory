# Roadmap — Staged Development Milestones

This roadmap uses **dependencies and review gates**, not calendar promises. Each phase
ends with a human review gate; later phases may be re-ordered or re-scoped at any gate.
Every implementation phase is delivered as one or more missions
([MISSION.md](../MISSION.md)) with small, reviewable Pull Requests.

```text
Phase 0 ──▶ Gate G1 ──▶ Phase 1 ──▶ Phase 2 ──▶ Phase 2.1 ──▶ Phase 2.2 ──▶ Phase 3 ──▶ ...
(M001)     (arch          core       collectors   hardening     operational   visibility
            approval)     backend    + registry   + ops ready   polish        + frontend
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

**Status: Gate G3 closed 2026-07-21** (M003 PR 1 #3 + PR 2 #4 merged; live RPSG01
deployment validated).

## Phase 2.1 — Observatory Hardening & Operational Readiness (M003.5)

Supervisor-added milestone (2026-07-21): consolidate Phase 2 into a production-ready
operational platform before Phase 3 visibility work begins. Canonical specification:
mission document M003.5 (supervisor mission directory). All metadata introduced here
must scale from a single node to multi-site fleets without schema changes.

1. **Continuous integration** — GitHub Actions (backend unit tests, collector tests,
   ClickHouse integration tests, lint/format); branch protection requires green
   checks before merge.
2. **Deployment hardening** — install / upgrade / uninstall / rollback procedures,
   *verified* (clean install, upgrade from previous release, reboot recovery,
   automatic service startup, pre-start configuration validation).
3. **Host Inventory & Fleet Registry enhancements** — explicit split between Host
   Inventory (this machine: hardware identity, structured multi-device storage
   inventory, OS inventory, maintenance status) and Fleet Registry (all nodes:
   reduced view locally as-is, enhanced view reserved for the central node,
   environment classification).
4. **Monitor improvements** — build/deployment metadata, system summary, storage
   inventory, richer Docker statistics, network interfaces, Recent Events (last 20).
5. **Token-usage architecture** — ownership documented (source, collector, future
   integration); no implementation.
6. **Security & release discipline** — release/deployment/rollback checklists,
   PR template, release tagging guidance.

**Dependencies:** Phase 2 (Gate G3 closed).
**Gate G3.5:** CI operational with required status checks; deployment package
validated; registry exposes complete hardware/OS identity; storage inventory supports
multiple devices; maintenance status visible; monitor refresh completes within one
second under normal operation; documentation complete; PRs merged.

## Phase 2.2 — Operational Polish & Runtime Corrections (M003.6)

Supervisor-added maintenance milestone (2026-07-22): close the operational gaps
found during the M003.5 production validation before Phase 3 begins. Canonical
specification: mission document M003.6 (supervisor mission directory); findings
recorded in [M003.6-notes.md](M003.6-notes.md).

1. **Claude Code detection** — configurable probe executable paths
   (`CLAUDE_BIN`, `OPENCLAW_BIN`) with PATH fallback; runtime version reports
   the Node.js actually running OpenClaw, not the system node.
2. **Persistent journald** — least-privilege persistent-journal host
   prerequisite documented ([deployment.md](deployment.md) §12), install-time
   readability warning, reboot-checklist journal step.
3. **Timezone rendering** — `DISPLAY_TZ` backend setting; "Last reboot" (and
   day boundaries) rendered in the display timezone with explicit offset;
   internal timestamps stay UTC.
4. **Documentation** — OpenClaw runtime dropped-systemEvent issue recorded as
   an external dependency with operational mitigations (no Observatory code).

**Dependencies:** Phase 2.1 (Gate G3.5).
**Gate:** acceptance criteria of M003.6 met (correct detection and versions on
the live monitor, timezone rendering verified, documentation merged, CI green,
no M003.5 regression).

## Phase 3 — Engineering and Cost Visibility + Initial Frontend

1. **GitHub integration** (poller: repos, branches, latest commit, active PRs, review
   status).
2. **Claude/API usage** (tokens, estimated cost per agent).
3. **Initial frontend dashboard** (fleet overview: agents, hosts, missions, PRs, alerts;
   **React SPA** for the Central Observatory per
   [SD-006](decisions/SD-006-react-spa-central-thin-ui-local.md); may start with a
   minimal feature set and grow, but on the SPA stack from the start).
4. **Dashboard authentication** (supervisor login).

**Dependencies:** Phase 2.2 (registry + mission data to display, hardened and
polished platform).
**Gate:** supervisor can answer "what is the fleet doing right now?" from the dashboard
alone.

### M004 follow-ups (recorded at PR3, awaiting scheduling)

- **Enforced read-only authorization for the `UI01` identity (security).**
  Today every authenticated identity may read *and* ingest events (SD-017
  binds ingestion to the caller's own `collector_id`). A leaked UI key can
  therefore submit forged telemetry attributed to `UI01`. Follow-up: an
  additive read-only marker per identity (e.g. a `READ_ONLY_IDS` setting)
  enforced with one check in the ingestion route, forward-compatible with
  the RBAC milestone — see
  [frontend-architecture.md](frontend-architecture.md) §8.
- **Running services (systemd) collector section (deferred from M004).**
  The host collector does not observe systemd services, so the Node
  details “Running Services” section honestly reads “Not reported”.
  Follow-up: an additive `services` section in the host-collector
  inventory payload (collector change only; the backend inventory
  projection is schema-flexible) — see
  [frontend-architecture.md](frontend-architecture.md) §11 item 3.

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
