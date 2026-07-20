# Backend Architecture

One page for future developers. The backend is a layered pipeline: every
telemetry event passes through the same stages, and each stage is replaceable
without touching the others.

```text
        HTTP
          ↓
   Authentication
          ↓
      Validation
          ↓
     Event Model
          ↓
  Domain Services  ←— background loops (offline detector, self-heartbeat)
          ↓
  Storage Interfaces
          ↓
      ClickHouse
```

## Layers

| Layer | Module(s) | Responsibility |
| --- | --- | --- |
| **HTTP** | `app/main.py`, `app/middleware.py`, `app/api/` | FastAPI app factory, versioned routing (`/api/v1`), request-size limits, request-ID context, structured JSON logging, Prometheus metrics. |
| **Authentication** | `app/auth.py` | `X-API-Key` verification (constant-time). Each key is bound to exactly one Fleet identity ([SD-017](../docs/decisions/SD-017-api-key-bound-to-fleet-identity.md)); a request may only submit events for the `collector_id` its key resolves to. The `CollectorAuthenticator` strategy interface is the extension point for a future JWT scheme. |
| **Validation** | `app/models/event.py` (`EventIn`) | Strict Pydantic validation of inbound payloads: types, timestamp formats, field constraints. Invalid input is rejected with `422` and counted in metrics. |
| **Event Model** | `app/models/event.py` (`Event`) | The canonical event: UUID, `collector_id`, `timestamp`, `event_type`, `payload`, `schema_version`, `received_at`. Every stored event has this shape regardless of source. |
| **Domain Services** (M003) | `app/services/` | Server-side semantics on top of the generic event pipeline. `pipeline.py`: per-event-type handlers (heartbeat validation, mission lifecycle transitions) — validation runs before persistence, projections after. `registry.py` + `seed.py`: Fleet Registry read-model (identity ⊕ derived telemetry) and create-only seeding from FLEET.md. `health.py`: computed health score (Healthy/Warning/Critical/Offline). `offline.py`: background offline detector (OFFLINE/ONLINE transition events) and the backend's own heartbeat. |
| **Storage Interfaces** | `app/storage/base.py` (`EventStorage`, `RegistryStorage`, `MissionStorage`) | Async abstractions. Routes and services depend only on these interfaces — backends are swappable (in-memory for tests/dev, ClickHouse for real). |
| **ClickHouse** | `app/storage/clickhouse.py`, `migrations/` | MergeTree-backed persistence ([SD-005](../docs/decisions/SD-005-clickhouse-central-sqlite-local.md)); mutable registry/mission state uses versioned rows on `ReplacingMergeTree` ([SD-018](../docs/decisions/SD-018-clickhouse-versioned-row-state.md), proposed). Schema evolves through plain, ordered SQL files in [`migrations/`](migrations/), applied in filename order at startup ([SD-016](../docs/decisions/SD-016-plain-sql-migrations.md)) — no migration framework. |

## Identity vs. telemetry vs. missions (M003)

Per M003 supervisor guidance the three concerns stay separate:

- **Identity** — the Fleet Registry (`fleet_registry` table) is the canonical
  source of identity. It is written only by startup seeding/administration;
  collectors can never create or modify identities (immutable Fleet IDs).
  Entries carry an `asset_type` (`agent`/`node`/`service`/`device`/`sensor`,
  FLEET.md): the physical host `RPSG01` is a *node*, while the Observatory
  backend running on it is a separate *service* asset `OBLN01` (Observatory
  Local Node deployment 01) that references its host through the explicit
  `host_fleet_id` relationship — placement, `deployment_role`, and
  `service_version` are registry fields, never parsed out of the Fleet ID.
  The backend emits its own heartbeat as `OBLN01`, so the Observatory is
  offline-detectable in its own registry (self-monitoring).
- **Telemetry** — heartbeats, system metrics, Docker status, and mission
  transitions are ordinary events in the append-only event stream; any future
  collector reuses the same envelope without model changes.
- **Missions** — `mission_update` events are the durable transition record;
  the `missions` table is a validated current-state projection (forward-only
  lifecycle — exact transition graph in `app/models/mission.py` — with
  computed duration). Collectors report *observed* mission state only; the
  projection is never a canonical mission record (the supervisor's mission
  documents are).

Read APIs (`GET /api/v1/fleet*`, `GET /api/v1/missions*`) are read-only joins
of identity with derived telemetry (connectivity, health score, last
heartbeat). M003 judgment calls and their resolutions are listed in
[docs/M003-open-questions.md](../docs/M003-open-questions.md).

## Operational endpoints

`GET /health` and `GET /metrics` sit outside the authenticated pipeline by
design: they are unauthenticated ([SD-013](../docs/decisions/SD-013-health-endpoint-unauthenticated.md),
[SD-014](../docs/decisions/SD-014-metrics-endpoint-unauthenticated.md)) and are
protected by network boundaries (loopback/tailnet in development; firewall,
reverse proxy, and internal networks in production), never by API keys.

`GET /monitor` (M003, [SD-020](../docs/decisions/SD-020-server-rendered-monitor-in-backend.md),
proposed) follows the same exposure model: the Observatory Monitor is a
server-rendered HTML instrument panel — agent health, mission progress, host
CPU/RAM/storage, Docker status, and the full fleet table with computed health
— built from the *same read models* the authenticated `/api/v1` routes serve.
`app/services/monitor.py` splits an async snapshot builder (reads
`RegistryService`/`MissionStorage`/`EventStorage`) from pure rendering
functions (stdlib string composition, every dynamic value HTML-escaped, meta
refresh instead of JavaScript); `app/api/monitor.py` is the thin route. It is
strictly read-only and adds no new storage or auth surface.

## Environments (architecture note)

| Environment | ClickHouse | Why |
| --- | --- | --- |
| **Development (Raspberry Pi 4)** | Native ClickHouse binary | Official ClickHouse Docker images require ARMv8.2 instructions; the Pi 4 (Cortex-A72, ARMv8.0) cannot run them. |
| **Production (VPS)** | Docker Compose | Full containerized stack on x86-64. |

The application does not care which one it talks to — configuration
(`CLICKHOUSE_HOST`/`PORT`) is identical; only the way ClickHouse is started
differs.

---

Written under Missions M002/M003 by A001-OC01-RPSG01 · decisions:
[docs/decisions/](../docs/decisions/README.md)
