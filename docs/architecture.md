# Architecture Proposal — OpenClaw Observatory

Status: **Proposal for human review (M001). Nothing here is implemented.**

Each major recommendation states *why*, its *trade-offs*, and at least one *reasonable
alternative*. Technology names are candidates with reasoning, not commitments; final
selection happens at the MVP architecture-approval gate ([roadmap.md](roadmap.md)).

## 1. System Overview

A hub-and-spoke design: a central Observatory service on a VPS, with lightweight
collectors on each observed host, all communicating over a private network.

```text
                         ┌────────────────────────── VPS ───────────────────────────┐
                         │                 OpenClaw Observatory                      │
                         │                                                           │
  Raspberry Pi SG01      │  ┌───────────┐   ┌──────────────┐   ┌─────────────────┐  │
 ┌──────────────────┐    │  │ Ingestion │──▶│ Storage       │──▶│ Dashboard (web) │  │
 │ host collector   │───▶│  │ REST API  │   │ • metadata DB │   └─────────────────┘  │
 │ agent collector  │───▶│  │ (vN)      │   │ • time-series │   ┌─────────────────┐  │
 └──────────────────┘    │  └───────────┘   └──────────────┘──▶│ /metrics (Prom)  │  │
        (Tailscale)      │        │                             └─────────────────┘  │
  Future hosts           │        ▼                             ┌─────────────────┐  │
 ┌──────────────────┐    │  ┌───────────┐    Fleet Registry  ──▶│ Alerting →      │  │
 │ collectors ...   │───▶│  │ Event bus │    Mission state      │ Telegram        │  │
 └──────────────────┘    │  │ (internal)│    Audit trail        └─────────────────┘  │
                         │  └───────────┘                                            │
  Pull-based sources     │        ▲                                                  │
 ┌──────────────────┐    │  ┌───────────┐                                            │
 │ GitHub API       │◀───│──│ Pollers   │  (GitHub, Claude usage, Bitaxe, ...)       │
 └──────────────────┘    │  └───────────┘                                            │
                         └───────────────────────────────────────────────────────────┘
```

## 2. Major Decisions

### 2.1 Central service on a VPS

- **Why:** collectors need one stable, always-on destination; observability must live
  outside the observed hosts; the dashboard needs a single authoritative origin.
- **Trade-offs:** single point of failure; monthly cost; another host to secure.
- **Alternative:** host on the Raspberry Pi (no new cost, but couples Mission Control to
  a fleet member and a home network); or SaaS observability (fast, but data leaves our
  control and fleet semantics don't fit). VPS is the deliberate middle ground.

### 2.2 Push-based collectors, plus pollers for external services

- **Why push (collectors → Observatory):** hosts behind NAT/home networks can always dial
  out; the Observatory needs no inbound access to any fleet host, which is a major
  security win (compromise of the Observatory does not grant access into hosts).
- **Why poll (Observatory → GitHub/Claude usage/Bitaxe):** these are external APIs or
  LAN devices with their own auth; polling centralizes credentials in one audited place.
- **Trade-offs:** push requires collector credentials on every host; offline detection
  becomes "absence of heartbeat" rather than a failed probe.
- **Alternative:** pull-based scraping of every host (Prometheus style) — clean for
  metrics but requires network reachability into each host and fits event/mission data
  poorly. A hybrid remains possible later: node exporters scraped by Prometheus, with the
  Observatory consuming Prometheus data.

### 2.3 Private network via Tailscale (or equivalent)

- **Why:** encrypted, identity-based connectivity between hosts with no ports exposed to
  the public internet; already proven for Pi↔VPS setups; minimal operational effort.
- **Trade-offs:** dependency on a third-party coordination plane; tailnet credentials
  become sensitive assets.
- **Alternatives:** WireGuard directly (no third party, more manual key/peer management);
  public HTTPS with mTLS (workable, but exposes a public attack surface). Headscale
  (self-hosted Tailscale control plane) is a future option if third-party dependency
  becomes a concern.

### 2.4 REST API with explicit versioning

- **Why REST/JSON:** simple, debuggable, universally supported by any collector language;
  our data rates are tiny, so performance-oriented protocols buy nothing.
- **Versioning:** URL-prefix versioning (`/api/v1/...`); additive changes within a
  version, breaking changes require a new version; collectors send their identity and
  schema version with every payload.
- **Trade-offs:** REST is weakly typed without discipline — mitigated by shared schemas
  (see §5) and contract validation at ingestion.
- **Alternatives:** gRPC (typed and efficient but heavier tooling for simple collectors);
  MQTT (nice for IoT-style telemetry, adds a broker to run; reconsider if device count
  grows into the dozens).

### 2.5 Storage: relational metadata + delegated time-series

- **Why relational (candidate: PostgreSQL; SQLite acceptable for earliest MVP):** the
  registry, missions, PRs, alerts, and audit trail are relational data with integrity
  requirements. Boring, proven, easy to back up.
- **Why delegate time-series:** numeric host metrics (CPU/RAM/temp) belong in a
  time-series store. Options in order of increasing machinery: Postgres tables with
  retention jobs (fine at MVP scale) → Prometheus (natural fit, we already expose
  `/metrics`) → VictoriaMetrics/Timescale if volume ever demands it.
- **Trade-offs:** running Postgres on a small VPS adds ops weight versus SQLite;
  SQLite limits concurrent writers. Recommendation: **decide at MVP gate**, defaulting
  to Postgres-in-container unless VPS sizing argues otherwise.
- **Alternative:** all-in-one time-series-plus-metadata stores — rejected for now, as
  they fit fleet/mission semantics poorly.

### 2.6 Event ingestion alongside metrics

- **Why:** much of what matters is event-shaped, not numeric: mission state changes,
  PR opened, agent commissioned, alert raised. Events land in the relational store with
  type, source identity, timestamp, and versioned payload, and drive the audit trail
  and alerting.
- **Trade-offs:** two ingestion shapes (metrics + events) to maintain.
- **Alternative:** logs-as-events pipelines (Loki etc.) — heavier than needed; revisit
  when log volume justifies it.

### 2.7 Frontend dashboard

- **Why a thin web UI:** the fleet-semantic views (registry, missions, approvals, cost)
  are the Observatory's reason to exist; Grafana can't model them well.
- **Recommendation:** server-rendered pages with minimal JavaScript for MVP — smallest
  attack surface, fastest to review; a richer SPA is justified only if interactivity
  demands grow.
- **Trade-offs:** less interactivity than a SPA initially.
- **Alternative:** SPA (React/Vue/Svelte) from day one — more polish, more supply-chain
  surface and build machinery; Grafana-only UI — rejected as primary UI (poor fit for
  registry/mission views) but embraced for metric charts.

### 2.8 Authentication and authorization

- **MVP:** single supervisor account for the dashboard (strong password + private-network
  exposure); unique bearer token per collector, individually revocable; all traffic
  encrypted (tailnet and/or TLS).
- **Future:** role-based access (viewer/operator/admin) and a separately authenticated,
  human-confirmed control surface (see [vision.md](vision.md) on monitoring vs. control).
- **Trade-offs:** tokens are simpler than mTLS but must be rotated and stored carefully.
- **Alternative:** mTLS per collector (stronger, heavier to operate); OAuth/OIDC (adds an
  identity-provider dependency; revisit for multi-user).

### 2.9 Module/plugin architecture

- **Why:** the capability list (agents, hosts, GitHub, Claude usage, Bitaxe, future
  systems) will keep growing; each domain should be a module with its own collector(s),
  schemas, and dashboard panel, registered against stable core interfaces (ingestion,
  storage, alerting, UI slots).
- **Trade-offs:** interface discipline costs some upfront design.
- **Alternative:** monolith-first, extract modules later — acceptable for MVP internals
  as long as *schemas and API contracts* stay modular from day one (that is the binding
  part of this recommendation).

### 2.10 Alerting

- **Why Telegram first:** it is already the fleet's human-attention channel
  ([AGENTS.md](../AGENTS.md)); alerts must be deduplicated and rate-limited so the
  channel retains signal value.
- **Trade-offs:** single notification channel initially.
- **Alternative:** Alertmanager-based routing once Prometheus enters the stack; email as
  a low-urgency fallback.

## 3. Cross-Cutting Concerns

- **Failure isolation:** ingestion validates and stores each payload independently; a
  malformed or hostile collector payload is quarantined and logged, never able to block
  the pipeline or corrupt other sources' data. Pollers (GitHub etc.) run as isolated
  tasks with their own retry/backoff.
- **Offline-agent handling:** absence of heartbeat beyond a per-source threshold flags
  the source as stale, fires an alert (deduplicated), and marks dashboard data with
  staleness rather than hiding it.
- **Data freshness:** every stored datum carries source timestamp and ingestion
  timestamp; the dashboard displays age, never pretending stale data is current.
- **Logs:** structured (JSON) application logs with retention per
  [requirements.md](requirements.md); no secrets or payload bodies containing sensitive
  content in logs.
- **Audit trail:** all state-changing operations record actor (human or agent identity),
  action, timestamp, and summary; privileged/control actions (future) get an
  append-only trail.
- **Secret management:** secrets injected via environment/host-local files or a secret
  manager; never in Git, images, telemetry, or logs. Full policy in
  [security.md](security.md).

## 4. Conceptual Data Flow

1. **Collect:** on each host, a host collector gathers CPU/RAM/disk/temperature/uptime;
   an agent collector gathers agent status, heartbeat, mission state, Claude Code
   status, and usage counters.
2. **Transmit:** collectors push JSON payloads (with identity, schema version, source
   timestamp) over the tailnet to `POST /api/v1/...`, authenticating with per-collector
   tokens; on failure they retry with backoff and (future) buffer locally.
3. **Poll:** the Observatory's pollers fetch GitHub repo/PR state, Claude/API usage, and
   (future) Bitaxe status on schedules, using centrally held, least-privilege credentials.
4. **Ingest:** payloads are authenticated, schema-validated, stamped with ingestion time,
   and written to storage; invalid payloads are quarantined and logged.
5. **Derive:** internal events update mission state, registry status, staleness flags,
   and evaluate alert rules.
6. **Present:** the dashboard renders fleet views from storage; `/metrics` exposes
   Prometheus-compatible series; Grafana may chart them.
7. **Alert:** qualifying events (deduplicated, rate-limited) are delivered to the
   supervisor via Telegram.
8. **Audit:** state changes and deliveries land in the audit trail.

## 5. Proposed Repository Structure

Future structure (directories are created only when they receive real content —
no empty scaffolding):

```text
.
├── README.md / AGENTS.md / MISSION.md / FLEET.md / ENGINEERING_PRINCIPLES.md
├── docs/                  # Architecture, requirements, security, deployment, roadmap
│   └── api/               # API documentation (versioned, once the API exists)
├── schemas/               # Shared telemetry/API schemas (single source of truth
│                          #   for backend, collectors, and frontend)
├── backend/               # Observatory service (API, ingestion, storage, alerting)
├── frontend/              # Dashboard UI (if/when separated from backend)
├── collectors/            # One subdirectory per collector (host-pi, openclaw-agent,
│                          #   github-poller, claude-usage, bitaxe, ...)
├── infra/                 # Deployment: compose files, infra-as-code, hardening notes
├── config/                # Example configuration only (*.example; never real secrets)
├── scripts/               # Operational and development scripts
├── tests/                 # Cross-cutting/integration tests (unit tests live with code)
└── fleet/                 # Fleet Registry records and mission records
    └── missions/          # Per-mission summaries (M001, M002, ...)
```

- **Why a monorepo:** one small team (of agents), shared schemas, atomic cross-cutting
  changes, single review surface.
- **Trade-off:** everything ships from one repo; acceptable far beyond current scale.
- **Alternative:** split repos per component — revisit only if independent release
  cadences or access boundaries demand it.

## 6. Open Questions for the Supervisor

1. **Database:** Postgres-in-container vs. SQLite for MVP (recommendation: Postgres,
   unless VPS sizing is tight).
2. **Time-series:** start with relational tables and adopt Prometheus at the Prometheus
   milestone, or deploy Prometheus from the start? (Recommendation: relational first,
   Prometheus at its milestone.)
3. **Backend language:** to be proposed at MVP gate (candidates: Python or TypeScript for
   velocity and ecosystem; Go for deployment simplicity). No commitment in M001.
4. **Tailscale vs. plain WireGuard** for the private network (recommendation: Tailscale
   for operational simplicity).

---

Related: [vision.md](vision.md) · [requirements.md](requirements.md) ·
[roadmap.md](roadmap.md) · [security.md](security.md) · [deployment.md](deployment.md)
