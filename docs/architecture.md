# Architecture — OpenClaw Observatory

Status: **Reviewed by the supervisor (M001). Nothing here is implemented yet.**
Approved decisions are recorded as SD-NNN records in
[docs/decisions/](decisions/README.md) and take precedence over any older wording in
this document. Where this document previously listed candidates, the decided choice is
now stated with the original alternatives kept for the record.

## 1. System Overview

A hub-and-spoke design: a central Observatory service on a VPS, with lightweight
collectors on each observed host, all communicating over a private network.

Per [SD-001](decisions/SD-001-central-and-local-observability.md), the Observatory is
designed in **two variants**:

- **Central Observability** — the full, world-class platform on a VPS (the diagram
  below): fleet-wide scope, ClickHouse storage, React SPA dashboard, pollers, alerting.
- **Local Observability** — a minimal on-host version: host-scoped telemetry, SQLite
  storage, thin web UI. It shares the same API contracts and schemas, and remains
  useful when the central Observatory is unreachable or not yet deployed.

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

### 2.1 Central service on a VPS — **decided: [SD-001](decisions/SD-001-central-and-local-observability.md)**

Central Observability runs on a VPS; additionally, a minimal Local Observability
variant runs on each local host (see §1).

- **Why:** collectors need one stable, always-on destination; observability must live
  outside the observed hosts; the dashboard needs a single authoritative origin.
- **Trade-offs:** single point of failure; monthly cost; another host to secure.
- **Alternative:** host on the Raspberry Pi (no new cost, but couples Mission Control to
  a fleet member and a home network); or SaaS observability (fast, but data leaves our
  control and fleet semantics don't fit). VPS is the deliberate middle ground.

### 2.2 Push-based collectors, plus pollers for external services — **approved: [SD-002](decisions/SD-002-push-based-collectors.md)**

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

### 2.3 Private network via Tailscale — **approved: [SD-003](decisions/SD-003-tailscale-networking.md), [SD-012](decisions/SD-012-networking-follows-sd-003.md)**

- **Why:** encrypted, identity-based connectivity between hosts with no ports exposed to
  the public internet; already proven for Pi↔VPS setups; minimal operational effort.
- **Trade-offs:** dependency on a third-party coordination plane; tailnet credentials
  become sensitive assets.
- **Alternatives:** WireGuard directly (no third party, more manual key/peer management);
  public HTTPS with mTLS (workable, but exposes a public attack surface). Headscale
  (self-hosted Tailscale control plane) is a future option if third-party dependency
  becomes a concern.

### 2.4 REST API with explicit versioning — **approved: [SD-004](decisions/SD-004-rest-api.md)**

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

### 2.5 Storage — **decided: [SD-005](decisions/SD-005-clickhouse-central-sqlite-local.md), [SD-009](decisions/SD-009-database-follows-sd-005.md), [SD-010](decisions/SD-010-relational-time-series-first.md)**

- **Decision:** **ClickHouse** for the Central Observatory; **SQLite** for the Local
  Observatory. PostgreSQL (the M001 candidate) is not selected.
- **Time-series:** relational tables first (in ClickHouse/SQLite) with retention jobs;
  **Prometheus integration later**, at its roadmap milestone (SD-010).
- **Why ClickHouse (central):** one store covers both event/metric volume (columnar,
  compression, fast aggregation — headroom far beyond fleet scale) and the registry/
  mission/audit metadata.
- **Why SQLite (local):** zero-dependency, embeddable, ideal for a minimal on-host
  variant with a single writer.
- **Trade-offs:** ClickHouse is append-oriented with eventual mutations, so
  registry/mission/audit models must be designed for it (versioned rows, ReplacingMergeTree-style
  patterns) rather than classic OLTP assumptions; it also adds more ops weight than
  SQLite/Postgres on a small VPS.
- **Alternatives considered:** PostgreSQL (+ retention jobs), all-in-one
  time-series-plus-metadata stores — recorded in SD-005 context; not selected.

### 2.6 Event ingestion alongside metrics

- **Why:** much of what matters is event-shaped, not numeric: mission state changes,
  PR opened, agent commissioned, alert raised. Events land in the relational store with
  type, source identity, timestamp, and versioned payload, and drive the audit trail
  and alerting.
- **Trade-offs:** two ingestion shapes (metrics + events) to maintain.
- **Alternative:** logs-as-events pipelines (Loki etc.) — heavier than needed; revisit
  when log volume justifies it.

### 2.7 Frontend dashboard — **decided: [SD-006](decisions/SD-006-react-spa-central-thin-ui-local.md)**

- **Decision:** a **full SPA using React** for the Central Observatory; a **thin web
  UI** (server-rendered, minimal JavaScript) for the Local Observatory.
- **Why an Observatory-owned UI at all:** the fleet-semantic views (registry, missions,
  approvals, cost) are the Observatory's reason to exist; Grafana can't model them well.
- **Why React SPA centrally:** rich interactivity for fleet views, clean
  frontend/backend separation over the versioned REST API ([SD-004](decisions/SD-004-rest-api.md)).
- **Trade-offs:** build tooling and supply-chain surface (mitigated by dependency
  auditing per [security.md](security.md)).
- **Alternatives considered:** server-rendered-only MVP (now the Local variant's
  approach); Grafana-only UI — rejected as primary UI but embraced for metric charts.

### 2.8 Authentication and authorization

- **MVP:** single supervisor account for the dashboard (strong password + private-network
  exposure); unique bearer token per collector, individually revocable; all traffic
  encrypted (tailnet and/or TLS).
- **Committed:** role-based access (viewer/operator/admin) and a separately
  authenticated, human-confirmed **privileged control surface** — a required
  capability per [SD-007](decisions/SD-007-privileged-control-required.md), delivered
  late-phase and human-gated (see [vision.md](vision.md) on monitoring vs. control).
- **Trade-offs:** tokens are simpler than mTLS but must be rotated and stored carefully.
- **Alternative:** mTLS per collector (stronger, heavier to operate); OAuth/OIDC (adds an
  identity-provider dependency; revisit for multi-user).

### 2.9 Module/plugin architecture — **approved from day one: [SD-008](decisions/SD-008-plugin-architecture-day-one.md)**

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

## 6. Resolved Supervisor Decisions

The open questions from the original M001 proposal are resolved. All decisions are
recorded in [docs/decisions/](decisions/README.md):

1. **Database:** ClickHouse (central) / SQLite (local) —
   [SD-005](decisions/SD-005-clickhouse-central-sqlite-local.md),
   [SD-009](decisions/SD-009-database-follows-sd-005.md).
2. **Time-series:** relational tables first; Prometheus integration later —
   [SD-010](decisions/SD-010-relational-time-series-first.md).
3. **Backend language:** Python — [SD-011](decisions/SD-011-python-backend.md).
4. **Private network:** Tailscale — [SD-003](decisions/SD-003-tailscale-networking.md),
   [SD-012](decisions/SD-012-networking-follows-sd-003.md).

---

Related: [vision.md](vision.md) · [requirements.md](requirements.md) ·
[roadmap.md](roadmap.md) · [security.md](security.md) · [deployment.md](deployment.md) ·
[decisions/](decisions/README.md)
