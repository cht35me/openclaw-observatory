# Requirements — OpenClaw Observatory

Requirements are grouped by scope stage:

- **[M001]** — satisfied by documentation in this mission
- **[MVP]** — required for the first working Observatory
- **[Future]** — planned, post-MVP
- **[Out of scope]** — explicitly not planned

Requirement IDs (`FR-x`, `NFR-x`, `SEC-x`) are stable and may be referenced by later
missions.

Supervisor decisions SD-001…SD-012 ([docs/decisions/](decisions/README.md)) resolve
the technology choices behind these requirements: two Observatory variants (central +
local), ClickHouse/SQLite storage, React SPA / thin web UI, Python backend, Tailscale,
and a required (late-phase, human-gated) privileged control surface.

## 1. Functional Requirements

### Fleet Registry

- **FR-1 [MVP]** Store agent identities per the model in [FLEET.md](../FLEET.md):
  global serial, agent ID, full identity, framework, host, role, status, supervisor,
  commissioning/retirement dates, channels, repository.
- **FR-2 [MVP]** Support lifecycle state transitions with timestamps and authorizing human.
- **FR-3 [Future]** Serve as runtime source of truth that agents query for their own
  identity and configuration.

### Agent Status

- **FR-4 [MVP]** Receive and store agent heartbeats (last-seen timestamp, basic status).
- **FR-5 [MVP]** Track per-agent: current mission, model and runtime version, Claude Code
  status, agent uptime.
- **FR-6 [MVP]** Flag agents as stale/offline when heartbeats stop (configurable threshold).
- **FR-7 [Future]** Mission queue and mission history per agent.

### Mission Tracking

- **FR-8 [MVP]** Record missions (ID, agent, state per [MISSION.md](../MISSION.md),
  timestamps, links to branch/PR).
- **FR-9 [Future]** Mission timelines, durations, and outcome statistics.

### Resource Monitoring

- **FR-10 [MVP]** Collect host telemetry from Raspberry Pi hosts: CPU usage, RAM usage,
  disk usage, CPU temperature, host uptime.
- **FR-11 [MVP]** Same metric set for the VPS host(s).
- **FR-12 [Future]** Workstations and additional platforms; Docker/service health.

### GitHub and Pull Request Visibility

- **FR-13 [MVP]** Per tracked repository: current branch(es) of interest, latest commit,
  active Pull Requests, PR review status.
- **FR-14 [Future]** Test/check status, broader GitHub activity feeds, multi-repo rollups.

### Claude and AI Usage Visibility

- **FR-15 [MVP]** Track token/API usage per agent and estimated cost, at least daily
  granularity.
- **FR-16 [Future]** Cost budgeting, per-mission attribution, anomaly detection
  (runaway usage alerts).

### Alerting

- **FR-17 [MVP]** Alert the supervisor (Telegram) on: agent offline, host unhealthy
  (thresholds), and ingestion failure. Alerts are deduplicated and rate-limited.
- **FR-18 [Future]** Configurable alert rules, severities, schedules (quiet hours), and
  acknowledgement tracking.

### Dashboard

- **FR-19 [MVP]** A web dashboard showing fleet overview: agents, status, current
  missions, host health, active PRs, recent alerts. For the Central Observatory this is
  a React SPA per [SD-006](decisions/SD-006-react-spa-central-thin-ui-local.md).
- **FR-20 [Future]** Drill-down views, historical charts, mission history, cost views.

### Integrations

- **FR-21 [MVP]** Expose Prometheus-compatible metrics for Observatory and fleet data.
- **FR-22 [Future]** Grafana interoperability (Observatory as data source or shared
  Prometheus), Bitaxe miner status collection, additional agent frameworks.

### Extensibility

- **FR-23 [MVP]** New telemetry types can be added without breaking existing collectors
  (versioned API, tolerant schemas).
- **FR-24 [Future]** Plugin/module mechanism for new collectors and dashboard panels.
  Schemas and API contracts are plugin-oriented from day one per
  [SD-008](decisions/SD-008-plugin-architecture-day-one.md).
- **FR-25 [Future]** Local Observability variant: a minimal on-host Observatory
  (SQLite storage, thin web UI, shared schemas) per
  [SD-001](decisions/SD-001-central-and-local-observability.md).

## 2. Non-Functional Requirements

### Security (summary — full detail in [security.md](security.md))

- **SEC-1 [MVP]** All collector→Observatory and user→Observatory traffic is authenticated
  and encrypted; private-network-first (Tailscale or equivalent).
- **SEC-2 [MVP]** Per-agent credentials; least privilege; revocable individually.
- **SEC-3 [MVP]** No secrets in the repository or in telemetry payloads.
- **SEC-4 [MVP]** Human approval gates for anything beyond read-only observation.
- **SEC-5 [Future]** Role-based authorization for additional users; privileged control
  surface with separate authentication — a **required** capability per
  [SD-007](decisions/SD-007-privileged-control-required.md), still late-phase and
  human-gated.

### Reliability

- **NFR-1 [MVP]** Collector failures are isolated: one broken collector must not corrupt
  or block others' data.
- **NFR-2 [MVP]** Agents and hosts keep working when the Observatory is down (monitoring
  is never on the fleet's critical path).
- **NFR-3 [MVP]** Ingestion is idempotent where feasible; duplicate deliveries must not
  double-count.
- **NFR-4 [Future]** Collector-side buffering to tolerate temporary Observatory outages.

### Availability

- **NFR-5 [MVP]** Single-instance deployment with automatic restart (container restart
  policy); informal target ~99% monthly — honest for one VPS, no HA claims.
- **NFR-6 [Future]** Backup/restore-based recovery objectives; HA only if the fleet ever
  justifies it.

### Performance

- **NFR-7 [MVP]** Dashboard overview loads in under ~2 seconds for a fleet of ≤10 agents
  and ≤10 hosts.
- **NFR-8 [MVP]** Telemetry ingestion at ~1 report/host/minute scale is trivially handled;
  design headroom of 100× current fleet size.

### Scalability

- **NFR-9 [MVP]** Schema and API designed for tens of agents/hosts without redesign.
- **NFR-10 [Future]** Hundreds of entities via horizontal read scaling and time-series
  delegation to Prometheus-class storage.

### Data Retention

- **NFR-11 [MVP]** Defined retention per data class (proposed starting points):
  high-resolution host metrics ~30 days; mission and registry records indefinitely;
  alerts/events ~180 days; raw ingestion logs ~14 days.
- **NFR-12 [Future]** Downsampling of old metrics; configurable retention; archival
  export.

### Auditability

- **NFR-13 [MVP]** All state-changing API operations are logged with actor, timestamp,
  and payload summary.
- **NFR-14 [Future]** Immutable audit trail for privileged/control actions.

### Authentication and Authorization

- **NFR-15 [MVP]** Dashboard access requires authentication (single supervisor account
  acceptable initially); API access requires per-collector tokens/keys.
- **NFR-16 [Future]** Multi-user roles (read-only, operator, admin); SSO if warranted.

### Operability

- **NFR-17 [MVP]** Health endpoint, structured logs, and self-metrics from day one.
- **NFR-18 [MVP]** Documented backup, restore, update, and rollback procedures
  ([deployment.md](deployment.md)).

## 3. M001 Documentation Requirements (this mission)

- **[M001]** Vision, requirements, architecture proposal, roadmap, security strategy,
  and deployment strategy documented under `docs/`.
- **[M001]** Governance documented: [AGENTS.md](../AGENTS.md), [MISSION.md](../MISSION.md),
  [ENGINEERING_PRINCIPLES.md](../ENGINEERING_PRINCIPLES.md).
- **[M001]** Fleet identity model and first registry entry documented: [FLEET.md](../FLEET.md).
- **[M001]** No production code, deployment, or implementation of any kind.

## 4. Out of Scope (explicitly not planned)

- General-purpose APM / log-analytics product ambitions.
- Executing missions or agent workloads inside the Observatory.
- Replacing GitHub as the system of record for code and review.
- Public/anonymous access of any kind.
- Autonomous control actions without human confirmation.
- During M001 specifically: any frontend, backend, API, database, Docker, exporters,
  dashboards, CI/CD, authentication implementation, or production configuration.

---

Related: [vision.md](vision.md) · [architecture.md](architecture.md) ·
[roadmap.md](roadmap.md) · [security.md](security.md) · [deployment.md](deployment.md)
