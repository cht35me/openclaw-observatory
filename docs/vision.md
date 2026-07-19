# Vision — OpenClaw Observatory as Mission Control

## The Mission Control Vision

A growing fleet of autonomous agents is only as trustworthy as a human's ability to see
what it is doing. The OpenClaw Observatory is the fleet's **Mission Control**: one place
where a supervisor can see every agent, every host, every mission, and every Pull Request
— and be alerted the moment something needs human judgment.

The guiding question for every Observatory feature: *does this help a human supervise
more agents with less attention, without losing control?*

## Intended Users

1. **The fleet supervisor (Martin)** — primary user. Needs at-a-glance fleet health,
   mission status, pending approvals, and cost visibility; wants alerts only when
   attention is genuinely required.
2. **Autonomous agents** — report telemetry and heartbeats; read the Fleet Registry and
   mission state as their source of truth.
3. **Future operators and collaborators** — scoped, read-only, or delegated views as the
   fleet outgrows a single human.

## Centralized VPS Deployment

The Observatory runs centrally on a VPS because the fleet is geographically and
administratively distributed (Raspberry Pi in Singapore today; more Pis, VPSes, and
workstations later). A central, always-on service:

- gives collectors a single, stable destination;
- survives any individual agent host going offline;
- serves the dashboard from one authoritative place;
- keeps observability *outside* the machines being observed.

Communication between hosts happens over a private network (Tailscale, per
[SD-003](decisions/SD-003-tailscale-networking.md)) rather than the public internet.
See [architecture.md](architecture.md) and [deployment.md](deployment.md).

## Two Deployment Variants

Per supervisor decision [SD-001](decisions/SD-001-central-and-local-observability.md),
the Observatory is designed in two versions:

- **Central Observability** — the full, world-class platform on a VPS: fleet-wide
  scope, ClickHouse storage, React SPA dashboard, pollers, and alerting.
- **Local Observability** — a minimal software version on each local host: host-scoped,
  SQLite storage, thin web UI; useful when the central Observatory is unreachable or
  not yet deployed.

Both variants share the same telemetry contracts and schemas.

## Multi-Platform Support

The Observatory is deliberately not OpenClaw-only. It observes:

- OpenClaw agents (first)
- Other autonomous-agent frameworks (later, via the same telemetry contracts)
- Raspberry Pi nodes, VPS infrastructure, and workstations
- GitHub repositories and Pull Requests
- Claude and AI usage
- Prometheus/Grafana ecosystems
- Bitaxe miners and other operational hardware

The unifying abstraction is the **telemetry contract**, not the platform: anything that
can speak the Observatory's ingestion API (or expose Prometheus-compatible metrics) can
be observed.

## Fleet-Scale Evolution

The design must remain sound as the fleet grows along three axes:

- **More agents** — from one (A001) to tens: registry, missions, and dashboards must not
  assume a single agent.
- **More hosts and locations** — the identity model ([FLEET.md](../FLEET.md)) already
  encodes platform, location, and host number.
- **More capability domains** — miners, home infrastructure, new services — absorbed as
  plugin modules rather than core rewrites.

Early versions optimize for one supervisor and a handful of agents; the architecture
avoids decisions that would cap growth at that scale.

## Observatory as a Control Plane

The long-term trajectory runs from *seeing* to *safely acting*:

1. **Observe** (first): status, health, missions, activity, cost.
2. **Alert**: route events that need attention to the supervisor.
3. **Coordinate** (later): mission queues, assignment visibility, registry as runtime
   source of truth.
4. **Control** (much later, human-gated): privileged actions such as pausing an agent or
   approving a mission — only with strong authentication, explicit human confirmation,
   and full audit trails. Per [SD-007](decisions/SD-007-privileged-control-required.md),
   privileged control is a **required** capability, not an optional aspiration — while
   remaining late-phase and human-gated.

## Boundaries Between Monitoring and Privileged Control

This boundary is a founding principle, not an afterthought:

- **Monitoring is read-only by construction.** Collectors push telemetry; the Observatory
  cannot reach into hosts. A compromised Observatory must not mean a compromised fleet.
- **Control actions are a separate, explicitly authorized surface** — separate
  credentials, separate audit trail, human confirmation for anything privileged, and
  introduced only in a late roadmap phase after review.
- **Agents never take instructions from telemetry channels.** Mission assignment remains
  on the engineering interface (SSH) with human authorship.

## Self-Observability

The Observatory watches the fleet; something must watch the Observatory. It will expose
its own health endpoints and Prometheus-compatible metrics, monitor its own ingestion
pipeline (staleness, error rates), and alert when *it* is degraded — because a silent
Mission Control is worse than none: it creates false confidence.

## Relationship with Prometheus and Grafana

The Observatory **complements** rather than replaces the Prometheus ecosystem:

- **Prometheus** is excellent at numeric time-series (CPU, RAM, temperatures). The
  Observatory exposes and/or scrapes Prometheus-compatible metrics instead of inventing
  a rival metrics format.
- **Grafana** is excellent at charts. The Observatory's own dashboard focuses on what
  Grafana does not model: fleet identity, missions, approvals, PRs, and cost — while
  remaining a good data source/neighbor for Grafana visualizations.

Fleet semantics live in the Observatory; heavy time-series machinery is delegated to the
tools built for it.

## Future Expansion Beyond OpenClaw

- Additional agent frameworks onboard by implementing the telemetry contract and
  receiving a framework prefix in the fleet identity model.
- New capability domains (e.g., Bitaxe miners, home automation, additional clouds)
  onboard as collector plugins and dashboard modules.
- The registry, mission model, and governance documents are written framework-neutrally
  so nothing structural changes when the second framework arrives.

## Non-Goals

- The Observatory is not a general-purpose APM/observability product.
- It is not an agent runtime and does not execute missions.
- It is not a replacement for GitHub (system of record for code) or for human review.

---

Related: [requirements.md](requirements.md) · [architecture.md](architecture.md) ·
[roadmap.md](roadmap.md) · [security.md](security.md) · [deployment.md](deployment.md)
