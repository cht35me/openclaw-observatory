# OpenClaw Observatory

Centralized Mission Control for autonomous agents and supporting infrastructure.

## Overview

The OpenClaw Observatory is the fleet-wide observability and supervision platform for
autonomous software engineering agents. It collects, stores, and presents operational
information from agents, hosts, repositories, and supporting services, giving a human
supervisor a single place to answer: **what is the fleet doing, is it healthy, and does
anything need my attention?**

The project is currently in its **documentation and architecture foundation phase**
(Mission M001). No production code exists yet, by design. The supervisor's M001 review
is complete: architecture and technology decisions **SD-001…SD-012** are recorded in
[docs/decisions/](docs/decisions/README.md).

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
- Surface AI usage: Claude Code status, token consumption, and estimated cost.
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

None of these are implemented yet. See [docs/roadmap.md](docs/roadmap.md).

## Current Project Phase

**M001 — Documentation and governance foundation.** This repository currently contains
only documentation: vision, requirements, architecture, roadmap, security strategy,
deployment strategy, fleet identity model, agent governance, and supervisor decision
records. The supervisor review of the M001 foundation produced decisions SD-001…SD-012
([docs/decisions/](docs/decisions/README.md)). Implementation begins only after the
M001 PR is approved and merged.

## Repository Structure

Current (M001):

```text
.
├── README.md                   # This file
├── AGENTS.md                   # How autonomous agents work in this repository
├── MISSION.md                  # Reusable mission lifecycle and governance
├── FLEET.md                    # Fleet identity model and registry
├── ENGINEERING_PRINCIPLES.md   # Permanent engineering principles
└── docs/
    ├── vision.md               # Mission Control vision
    ├── requirements.md         # Functional and non-functional requirements
    ├── architecture.md         # Proposed high-level architecture
    ├── roadmap.md              # Staged development milestones
    ├── security.md             # Security strategy and threat model
    ├── deployment.md           # Intended deployment lifecycle
    └── decisions/              # Supervisor decision records (SD-NNN-name.md)
```

The proposed future structure (backend, frontend, collectors, schemas, infra, tests) is
documented in [docs/architecture.md](docs/architecture.md#5-proposed-repository-structure).
Implementation directories are intentionally not created until they contain real work.

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
| [docs/decisions/](docs/decisions/README.md) | Supervisor decision records (SD-001…SD-012) |
| [docs/roadmap.md](docs/roadmap.md) | Staged milestones with dependencies and gates |
| [docs/security.md](docs/security.md) | Threat model and security strategy |
| [docs/deployment.md](docs/deployment.md) | Deployment lifecycle and operations |

---

Maintained by agent **A001-OC01-RPSG01** under the supervision of **Martin**.
