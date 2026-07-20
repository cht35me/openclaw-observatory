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
  Storage Interface
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
| **Storage Interface** | `app/storage/base.py` (`EventStorage`) | Async abstraction (`startup/shutdown/ping/insert/query`). Routes depend only on this interface — backends are swappable (`InMemoryEventStorage` for tests/dev, ClickHouse for real). |
| **ClickHouse** | `app/storage/clickhouse.py`, `migrations/` | MergeTree-backed persistence ([SD-005](../docs/decisions/SD-005-clickhouse-central-sqlite-local.md)). Schema evolves through plain, ordered SQL files in [`migrations/`](migrations/), applied in filename order at startup ([SD-016](../docs/decisions/SD-016-plain-sql-migrations.md)) — no migration framework. |

## Operational endpoints

`GET /health` and `GET /metrics` sit outside the authenticated pipeline by
design: they are unauthenticated ([SD-013](../docs/decisions/SD-013-health-endpoint-unauthenticated.md),
[SD-014](../docs/decisions/SD-014-metrics-endpoint-unauthenticated.md)) and are
protected by network boundaries (loopback/tailnet in development; firewall,
reverse proxy, and internal networks in production), never by API keys.

## Environments (architecture note)

| Environment | ClickHouse | Why |
| --- | --- | --- |
| **Development (Raspberry Pi 4)** | Native ClickHouse binary | Official ClickHouse Docker images require ARMv8.2 instructions; the Pi 4 (Cortex-A72, ARMv8.0) cannot run them. |
| **Production (VPS)** | Docker Compose | Full containerized stack on x86-64. |

The application does not care which one it talks to — configuration
(`CLICKHOUSE_HOST`/`PORT`) is identical; only the way ClickHouse is started
differs.

---

Written under Mission M002 by A001-OC01-RPSG01 · decisions:
[docs/decisions/](../docs/decisions/README.md)
