# OpenClaw Observatory

Centralized Mission Control for autonomous agents and supporting infrastructure.

## Overview

The OpenClaw Observatory is the fleet-wide observability and supervision platform for
autonomous software engineering agents. It collects, stores, and presents operational
information from agents, hosts, repositories, and supporting services, giving a human
supervisor a single place to answer: **what is the fleet doing, is it healthy, and does
anything need my attention?**

The M001 foundation phase (documentation, architecture, governance) is complete:
architecture and technology decisions **SD-001…SD-020** (approved/accepted) are
recorded in
[docs/decisions/](docs/decisions/README.md). Mission **M002** delivered the first
production code: the core backend skeleton in [backend/](backend/) — an authenticated,
versioned ingestion API backed by ClickHouse, with health, metrics, and structured
logging. Mission **M003** adds Observatory self-awareness in two PRs: **PR 1**
(merged) delivered the Fleet Registry, mission lifecycle tracking, heartbeat
and offline/online processing, read-only APIs, backend self-monitoring, and the
refined fleet identity model; **PR 2** delivers the deployable RPSG01
collectors, the real RPSG01 installation, and the lightweight **Observatory
Monitor** (`GET /monitor`). See [Backend Service](#backend-service-m002m003)
and [Collectors](#collectors-m003-pr-2).

The Observatory is designed in two variants
([SD-001](docs/decisions/SD-001-central-and-local-observability.md)):

- **Central Observability** — the full platform on a VPS: ClickHouse storage, React SPA
  dashboard, Python backend, Tailscale networking.
- **Local Observability** — a minimal on-host version: SQLite storage, thin web UI.

## Purpose

- Provide a single control plane for observing a growing fleet of autonomous agents.
- Track agent identity, lifecycle, missions, and status through a central Fleet Registry.
- Monitor the health of the hosts agents run on (Raspberry Pi nodes, VPS instances, workstations).
- Surface engineering activity: repositories, branches, commits, Pull Requests, and reviews.
- Surface AI usage: Claude Code status, token consumption, and estimated cost
  (token accounting ownership:
  [docs/token-usage-architecture.md](docs/token-usage-architecture.md)).
- Alert a human supervisor when attention is required — and stay quiet otherwise.

## Long-Term Vision

The Observatory will run centrally on a VPS and receive telemetry from distributed
collectors across multiple platforms and locations, including:

- OpenClaw agents (and, later, other autonomous-agent frameworks)
- Raspberry Pi nodes, VPS infrastructure, and workstations
- GitHub repositories and Pull Requests
- Claude and AI usage metrics
- Prometheus and Grafana ecosystems
- Bitaxe miners and other operational hardware
- Future infrastructure and operational systems

See [docs/vision.md](docs/vision.md) for the full vision.

## Primary Users

- **Fleet supervisor (human):** reviews fleet status, approves work, responds to alerts.
- **Autonomous agents:** report telemetry, mission status, and heartbeats; consume the
  Fleet Registry as the source of truth for identity.
- **Future operators/collaborators:** read-only or scoped access to dashboards.

## High-Level Capabilities (Planned)

- Fleet Registry: agent identity, lifecycle, roles, and commissioning records
- Mission tracking: current mission, mission queue, and mission history per agent
- Agent status: heartbeats, uptime, model/runtime versions, Claude Code status
- Host health: CPU, RAM, disk, temperature, and uptime for Pis, VPSes, and workstations
- Engineering visibility: repository, branch, latest commit, active PRs, review and test status
- AI usage: token and API usage with estimated cost
- Integrations: Prometheus-compatible metrics, Grafana interoperability, Bitaxe status
- Alerting: notify the supervisor (e.g., via Telegram) only when attention is required
- Plugin modules for future capabilities

The ingestion API and storage layer exist as of M002; the Fleet Registry, mission
tracking, agent/host telemetry, heartbeats, offline detection, and health scores
exist as of M003. The remaining capabilities arrive in later missions. See
[docs/roadmap.md](docs/roadmap.md).

## Current Project Phase

**M003 — Observatory self-awareness (Phase 2).** On top of the merged M002 backend
(FastAPI service, ClickHouse storage, collector API-key authentication, Prometheus
metrics, structured JSON logging, tests, Docker packaging), M003 delivers:

**PR 1 (this branch):**

- **Fleet Registry** — authoritative identity inventory seeded from
  [FLEET.md](FLEET.md) (RPSG01, A001, OBLN01), with asset types
  (`agent`/`node`/`service`/`device`/`sensor`), explicit host relationships
  (`host_fleet_id`), nicknames, capabilities, arbitrary filter tags, and
  immutable Fleet IDs. The physical Pi (`RPSG01`, a *node*) and the
  Observatory deployment running on it (`OBLN01`, a *service*) are distinct
  assets.
- **Mission tracking** — persistent lifecycle
  (Created → Queued → Assigned → Running → Review → Completed), forward-only
  validated transitions as events, computed duration, PR reference and commit SHA.
- **Heartbeats & offline detection** — versioned heartbeats
  (collector type/version, schema version), configurable timeout, OFFLINE/ONLINE
  transition events, Prometheus fleet metrics, and the backend's own
  self-heartbeat (`OBLN01` monitors itself).
- **Health score** — Healthy/Warning/Critical/Offline computed from heartbeat age,
  CPU temperature, disk, RAM, and collector failures.

**PR 2** (branch `a001/m003-collectors-monitor`, supervisor-confirmed follow-up):
the deployable **Raspberry Pi host collector** (CPU/temperature/RAM/disk/load/
uptime/network + Docker telemetry), the **OpenClaw agent collector** (agent
status, mission updates, runtime/model), real installation and validation on
RPSG01, and the lightweight **Observatory Monitor** web panel.

Judgment calls and their resolutions for the Gate G3 review are in
[docs/M003-open-questions.md](docs/M003-open-questions.md).

## Backend Service (M002/M003)

The backend lives in [backend/](backend/): a Python 3.13 / FastAPI service that
accepts authenticated telemetry events over a versioned REST API (SD-004) and stores
them in ClickHouse (SD-005). The layered design is documented in
[backend/ARCHITECTURE.md](backend/ARCHITECTURE.md); the implementation questions
raised during M002 were resolved at the Gate G2 review as **SD-013…SD-017**
(see [backend/OPEN_QUESTIONS.md](backend/OPEN_QUESTIONS.md)).

### Architecture note: ClickHouse per environment

| Environment | ClickHouse | Why |
| --- | --- | --- |
| **Development (Raspberry Pi 4)** | Native ClickHouse binary | Official ClickHouse Docker images require ARMv8.2 instructions; the Pi 4 (Cortex-A72, ARMv8.0) cannot run them. |
| **Production (VPS)** | Docker Compose | Full containerized stack on x86-64. |

The backend is agnostic — only `CLICKHOUSE_HOST`/`CLICKHOUSE_PORT` differ.

### One-command startup (Docker)

```bash
cp .env.example .env    # then replace every placeholder value
docker compose up
```

This starts ClickHouse (internal-only; no host port) and the backend on
`127.0.0.1:8000` by default. Real secrets belong only in the untracked `.env`.

### Endpoints

| Endpoint | Auth | Description |
| --- | --- | --- |
| `GET /health` | none ([SD-013](docs/decisions/SD-013-health-endpoint-unauthenticated.md)) | Status (`ok`/`degraded`), version, uptime, DB connectivity. Always HTTP 200; a DB outage flips `status` to `degraded` (a liveness probe must not restart a healthy API process). |
| `GET /metrics` | none, internal-only ([SD-014](docs/decisions/SD-014-metrics-endpoint-unauthenticated.md)) | Prometheus metrics: request count/latency, ingestion successes/failures, DB latency, fleet gauges, heartbeat latency, offline transitions. Protected by network boundaries (firewall/reverse proxy/tailnet), never exposed publicly. |
| `GET /monitor` | none, internal-only ([SD-020](docs/decisions/SD-020-server-rendered-monitor-in-backend.md)) | **Observatory Monitor** — server-rendered HTML instrument panel: OpenClaw agent health, mission progress, host CPU/RAM/storage, Docker containers, fleet & service health. Stdlib rendering, meta-refresh, no JS/build toolchain; loopback/tailnet exposure only. |
| `POST /api/v1/events` | `X-API-Key` | Ingest one telemetry event (strictly validated JSON). Returns `202` with the assigned event UUID. Each key is bound to one collector identity ([SD-017](docs/decisions/SD-017-api-key-bound-to-fleet-identity.md)); submitting another `collector_id` returns `403`. Event types with server-side semantics (`heartbeat`, `mission_update`) are validated against their payload schemas and drive projections. |
| `GET /api/v1/fleet` | `X-API-Key` | List all Fleet Registry assets with derived connectivity, last heartbeat, and computed health score (read-only). |
| `GET /api/v1/fleet/{id}` | `X-API-Key` | One registry asset by Fleet ID, or `404`. |
| `GET /api/v1/missions` | `X-API-Key` | List tracked missions with lifecycle state and computed duration (read-only). |
| `GET /api/v1/missions/{id}` | `X-API-Key` | One mission by ID (e.g. `M003`), or `404`. |

Example ingestion:

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/events \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: <key bound to collector_id "demo" in API_KEYS>' \
  -d '{"collector_id":"demo","timestamp":"2026-07-19T12:00:00Z","event_type":"synthetic","payload":{"temperature":41,"status":"ok"}}'
```

### Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `CLICKHOUSE_HOST` | `localhost` | ClickHouse hostname (`clickhouse` inside compose) |
| `CLICKHOUSE_PORT` | `8123` | ClickHouse HTTP port |
| `CLICKHOUSE_DATABASE` | `observatory` | Database (created on startup if missing) |
| `CLICKHOUSE_USERNAME` | `default` | Database user (`observatory` in compose) |
| `CLICKHOUSE_PASSWORD` | *(empty)* | Database password — secret, env-only |
| `API_KEYS` | *(empty ⇒ reject all)* | Collector key↔identity bindings ([SD-017](docs/decisions/SD-017-api-key-bound-to-fleet-identity.md)): comma-separated `collector_id:key` pairs or JSON object — secret, env-only |
| `LOG_LEVEL` | `INFO` | Structured-log level |
| `APP_VERSION` | `0.1.0` | Version reported by `/health` and metrics |
| `MAX_REQUEST_BYTES` | `1048576` | Request body size limit (middleware-enforced) |
| `FLEET_ID` | `OBLN01` | The backend's own Fleet Registry *service* identity (it heartbeats itself; FLEET.md service scheme) |
| `COLLECTOR_NAME` | `observatory-backend` | Name reported in the backend's own heartbeat |
| `HEARTBEAT_INTERVAL` | `30` | Seconds between the backend's own heartbeats |
| `OFFLINE_TIMEOUT` | `90` | Heartbeat age (seconds) after which an asset is OFFLINE |
| `OFFLINE_CHECK_INTERVAL` | `15` | Seconds between offline-detector sweeps |
| `BACKGROUND_TASKS_ENABLED` | `true` | Master switch for background loops (tests disable) |
| `HEALTH_*` | see `app/config.py` | Health-score thresholds (CPU temp, disk, RAM, heartbeat age, failures) |

Collector-side configuration (`HEARTBEAT_INTERVAL`, `FLEET_ID`,
`COLLECTOR_NAME`, `MISSION_POLL_INTERVAL`, …) is documented in
[collectors/README.md](collectors/README.md).

## Collectors (M003 PR 2)

Push-based telemetry producers ([SD-002](docs/decisions/SD-002-push-based-collectors.md))
live in [collectors/](collectors/): the **Raspberry Pi host collector**
(system metrics, Docker telemetry, heartbeats) and the **OpenClaw agent
collector** (agent status, mission updates with the first-sync backfill rule,
heartbeats). They are standard-library-only Python
([SD-019](docs/decisions/SD-019-stdlib-only-collectors.md)) — no
`pip install` on fleet hosts — and ship with systemd user units. Both are
installed and running on RPSG01 (supervisor-authorized, M003 PR 2). The
backend-side contract (payload schemas for `heartbeat` and `mission_update`,
SD-017 key↔identity binding, registry-known Fleet IDs) is fully defined and
enforced by this backend. See [collectors/README.md](collectors/README.md).

### RPSG01 runbook (native deployment, as executed)

The full stack runs on RPSG01 as **systemd user units** (`loginctl
enable-linger` keeps them up without a session):

| Unit | What | Where |
| --- | --- | --- |
| `observatory-clickhouse` | Native ClickHouse binary (Pi 4 cannot run CH docker images), loopback `8123`/`9000` | [deploy/systemd/](deploy/systemd/) |
| `observatory-backend` | uvicorn from `backend/.venv`, loopback `127.0.0.1:8000` | [deploy/systemd/](deploy/systemd/) |
| `observatory-host-collector` | RPSG01 system + Docker telemetry | [collectors/systemd/](collectors/systemd/) |
| `observatory-agent-collector` | A001 agent status + mission tracking | [collectors/systemd/](collectors/systemd/) |

Configuration and secrets live in untracked `~/.config/observatory/*.env`
files (chmod 600; API keys generated with `openssl rand -hex 32`, one key per
fleet identity per [SD-017](docs/decisions/SD-017-api-key-bound-to-fleet-identity.md));
the repository carries placeholder examples only
([deploy/backend.example.env](deploy/backend.example.env),
[collectors/config.example.env](collectors/config.example.env)).
Installation steps as executed: [collectors/README.md](collectors/README.md#deployment-on-rpsg01-as-executed-m003-pr-2).
The monitor is then live at `http://127.0.0.1:8000/monitor`.

Lifecycle operations are scripted (Phase 2.1, M003.5 §2): install, upgrade,
rollback, and uninstall live in [deploy/scripts/](deploy/scripts/) with the
runbook in [deploy/README.md](deploy/README.md). Backend and collectors
validate their configuration **before** serving and fail fast with a clear
error on missing/invalid values; the scripts run the same validation before
any restart. Reboot-recovery expectations:
[docs/deployment.md §12](docs/deployment.md#12-rpsg01-native-deployment-package-phase-21).

### Local development and tests

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest            # ClickHouse integration tests auto-skip if no server
.venv/bin/python -m pytest ../collectors                      # stdlib-only collector suite
.venv/bin/ruff check app tests ../collectors                  # lint (config: root pyproject.toml)
.venv/bin/ruff format --check app tests ../collectors
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000   # run against env config
```

Every PR must pass the [CI workflow](.github/workflows/ci.yml) (backend,
collectors, ClickHouse integration, Ruff) — the same commands, enforced as
required status checks on `main`. See
[docs/release-process.md](docs/release-process.md).

The test suite runs entirely offline using an in-memory storage backend; tests in
`tests/test_clickhouse_integration.py` execute only when a ClickHouse server is
reachable (e.g. via `docker compose up clickhouse`).

## Frontend — Operations Console (M004)

[frontend/](frontend/) contains the React operations console (Vite +
TypeScript strict + React Router + TanStack Query + TailwindCSS/shadcn-ui):
dashboard, fleet cards, node details (Host Inventory + Docker), services
runtime view, and an auto-refreshing events timeline. Design and rationale:
[docs/frontend-architecture.md](docs/frontend-architecture.md).

```bash
cd frontend
npm ci                 # locked dependencies (package-lock.json)
npm run dev            # dev server; proxies /api + /health to 127.0.0.1:8000
npm test -- --run      # Vitest + React Testing Library
npm run lint && npm run format:check && npm run typecheck
npm run build          # production build → frontend/dist/
```

In production the backend serves `frontend/dist` itself, same-origin — no
extra process or proxy; without a build it runs exactly as before. See
[docs/deployment.md](docs/deployment.md) §13. The console authenticates with
a dedicated `UI01` API key entered under Settings (SD-017); the zero-JS
`/monitor` page remains the emergency panel.

## Repository Structure

```text
.
├── README.md                   # This file
├── AGENTS.md                   # How autonomous agents work in this repository
├── MISSION.md                  # Reusable mission lifecycle and governance
├── FLEET.md                    # Fleet identity model and registry
├── ENGINEERING_PRINCIPLES.md   # Permanent engineering principles
├── docker-compose.yml          # Development stack: backend + ClickHouse
├── .env.example                # Configuration template (placeholders only)
├── backend/                    # Observatory backend service (M002)
│   ├── app/                    # FastAPI application (api/, storage/, models/)
│   ├── migrations/             # Ordered SQL schema migrations (SD-016)
│   ├── tests/                  # Pytest suite (offline; CH integration auto-skips)
│   ├── ARCHITECTURE.md         # One-page layered architecture overview
│   ├── Dockerfile              # Slim, non-root container image
│   ├── requirements*.txt       # Pinned dependencies
│   └── OPEN_QUESTIONS.md       # M002 questions — resolved as SD-013…SD-017
├── collectors/                 # Stdlib-only fleet collectors (M003 PR 2, SD-019)
│   ├── observatory_collectors/ # host_pi + openclaw_agent packages
│   ├── systemd/                # Collector systemd user units
│   └── tests/                  # Offline collector suite (fixture-driven)
├── deploy/                     # Native RPSG01 deployment (units, example env,
│                               #   install/upgrade/rollback/uninstall scripts)
└── docs/
    ├── vision.md               # Mission Control vision
    ├── requirements.md         # Functional and non-functional requirements
    ├── architecture.md         # Proposed high-level architecture
    ├── roadmap.md              # Staged development milestones
    ├── security.md             # Security strategy and threat model
    ├── deployment.md           # Intended deployment lifecycle
    ├── M003-open-questions.md  # M003 judgment calls and resolutions (Gate G3)
    └── decisions/              # Supervisor decision records (SD-NNN-name.md)
```



The full target structure (frontend, collectors, schemas, infra, tests) is documented
in [docs/architecture.md](docs/architecture.md#5-proposed-repository-structure).
Implementation directories are created only when they receive real content.

## Development Workflow

1. Work happens on dedicated feature branches — never directly on `main`.
2. Documentation precedes implementation; architecture precedes code.
3. Changes are proposed through small, focused Pull Requests.
4. A human supervisor reviews and approves every merge.
5. Agents follow the governance defined in [AGENTS.md](AGENTS.md) and the mission
   lifecycle defined in [MISSION.md](MISSION.md).

## Security Posture

Security by default: least privilege, no secrets in the repository, human approval gates
before merge or deployment, private networking (e.g., Tailscale) for host-to-host
communication, and full auditability of agent actions. See [docs/security.md](docs/security.md).

## Deployment Direction

Development on Raspberry Pi SG01 → GitHub Pull Requests → human review → staging on VPS →
production on VPS, with distributed collectors connecting from remote hosts over a private
network. Container-based deployment is the leading candidate. Nothing is deployed during
M001. See [docs/deployment.md](docs/deployment.md).

## Documentation

| Document | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Agent contribution rules and governance |
| [MISSION.md](MISSION.md) | Mission lifecycle, states, and Definition of Done |
| [FLEET.md](FLEET.md) | Fleet identity model and Fleet Registry |
| [ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md) | Permanent engineering principles |
| [docs/vision.md](docs/vision.md) | Long-term Mission Control vision |
| [docs/requirements.md](docs/requirements.md) | Requirements: M001, MVP, future, out of scope |
| [docs/architecture.md](docs/architecture.md) | Architecture, decisions, and trade-offs |
| [docs/decisions/](docs/decisions/README.md) | Supervisor decision records (SD-001…SD-017 approved; SD-018…SD-019 proposed) |
| [docs/roadmap.md](docs/roadmap.md) | Staged milestones with dependencies and gates |
| [docs/security.md](docs/security.md) | Threat model and security strategy |
| [docs/deployment.md](docs/deployment.md) | Deployment lifecycle and operations |
| [docs/release-process.md](docs/release-process.md) | Release/deployment/rollback checklists, CI required checks, tagging |

---

Maintained by agent **A001-OC01-RPSG01** under the supervision of **Martin**.
