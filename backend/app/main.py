"""Application factory and ASGI entry point.

``create_app()`` wires configuration, logging, metrics, authentication,
storage, middleware, and routers together. Tests inject fakes through the
factory parameters; production uses the defaults (environment-driven settings
plus ClickHouse storage per SD-005).

Run locally::

    uvicorn --factory app.main:build_app --host 127.0.0.1 --port 8000

The factory validates configuration *before* the server binds its port
(M003.5 §2): a missing or invalid environment exits non-zero with a clear
message instead of serving requests it cannot authenticate or store.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response

from app.api.health import router as health_router
from app.api.monitor import router as monitor_router
from app.api.prometheus import router as prometheus_router
from app.api.v1 import routers as v1_routers
from app.auth import ApiKeyAuthenticator
from app.config import ConfigurationError, Settings, load_settings
from app.logging import configure_logging
from app.metrics import AppMetrics
from app.middleware import RequestContextMiddleware, RequestSizeLimitMiddleware
from app.services.offline import BackendHeartbeat, OfflineDetector
from app.services.pipeline import build_pipeline
from app.services.registry import RegistryService
from app.services.seed import seed_registry
from app.services.startup_event import record_service_start
from app.spa import mount_frontend, resolve_dist_dir
from app.storage.base import (
    EventStorage,
    HostInventoryStorage,
    MissionStorage,
    RegistryStorage,
    StorageError,
)
from app.storage.clickhouse import (
    ClickHouseEventStorage,
    ClickHouseHostInventoryStorage,
    ClickHouseMissionStorage,
    ClickHouseRegistryStorage,
)

_logger = logging.getLogger("observatory.app")


def create_app(
    settings: Settings | None = None,
    storage: EventStorage | None = None,
    registry_storage: RegistryStorage | None = None,
    mission_storage: MissionStorage | None = None,
    inventory_storage: HostInventoryStorage | None = None,
) -> FastAPI:
    """Build a fully wired FastAPI application.

    Args:
        settings: Optional pre-built settings (defaults to environment-driven
            :func:`app.config.load_settings`).
        storage: Optional event-storage backend (defaults to ClickHouse).
            Tests pass an :class:`~app.storage.memory.InMemoryEventStorage`.
        registry_storage: Optional Fleet Registry backend (defaults to
            ClickHouse; tests pass the in-memory variant).
        mission_storage: Optional mission projection backend (same pattern).
        inventory_storage: Optional Host Inventory projection backend
            (M003.5 §3; same pattern).
    """
    settings = settings or load_settings()
    configure_logging(settings.log_level)

    metrics = AppMetrics.create(version=settings.app_version)
    if storage is None:
        storage = ClickHouseEventStorage(settings, on_db_latency=metrics.observe_db_latency)
    if registry_storage is None:
        registry_storage = ClickHouseRegistryStorage(
            settings, on_db_latency=metrics.observe_db_latency
        )
    if mission_storage is None:
        mission_storage = ClickHouseMissionStorage(
            settings, on_db_latency=metrics.observe_db_latency
        )
    if inventory_storage is None:
        inventory_storage = ClickHouseHostInventoryStorage(
            settings, on_db_latency=metrics.observe_db_latency
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.started_at_monotonic = time.monotonic()
        try:
            # Event storage first: it owns schema bootstrap (SD-016), so the
            # registry/mission tables exist before their backends start.
            await storage.startup()
            await registry_storage.startup()
            await mission_storage.startup()
            await inventory_storage.startup()
            created = await seed_registry(registry_storage)
            if created:
                _logger.info("fleet registry seeded with %d asset(s)", created)
            _logger.info("storage backends ready")
            # Recent-events visibility (M003.5 §4): backend start is a
            # notable lifecycle event. Best effort — a failed insert must
            # never block startup.
            try:
                await record_service_start(settings, storage)
            except StorageError:
                _logger.warning("could not record service_start event")
        except StorageError:
            # Start in degraded mode: /health reports it, collectors get 503
            # on ingest, and the app keeps retrying lazily on later requests.
            _logger.exception("storage backend unavailable at startup; running degraded")

        background_tasks: list[asyncio.Task[None]] = []
        if settings.background_tasks_enabled:
            background_tasks = [
                asyncio.create_task(
                    app.state.offline_detector.run_forever(), name="offline-detector"
                ),
                asyncio.create_task(
                    app.state.backend_heartbeat.run_forever(), name="backend-heartbeat"
                ),
            ]
        yield
        for task in background_tasks:
            task.cancel()
        for task in background_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await storage.shutdown()
        await registry_storage.shutdown()
        await mission_storage.shutdown()
        await inventory_storage.shutdown()

    app = FastAPI(
        title="OpenClaw Observatory API",
        version=settings.app_version,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,  # No anonymous schema/docs exposure (security.md §3).
    )

    app.state.settings = settings
    app.state.storage = storage
    app.state.metrics = metrics
    app.state.authenticator = ApiKeyAuthenticator(settings.api_key_bindings)
    app.state.started_at_monotonic = time.monotonic()  # refined in lifespan

    # --- M003 services: registry read-models, ingestion pipeline, offline
    #     detection, backend self-heartbeat. ---
    app.state.registry_storage = registry_storage
    app.state.mission_storage = mission_storage
    app.state.inventory_storage = inventory_storage
    app.state.registry_service = RegistryService(settings, registry_storage, storage)
    app.state.pipeline = build_pipeline(
        settings, registry_storage, mission_storage, metrics, inventory_storage
    )
    app.state.offline_detector = OfflineDetector(settings, registry_storage, storage, metrics)
    app.state.backend_heartbeat = BackendHeartbeat(
        settings,
        storage,
        uptime_fn=lambda: time.monotonic() - app.state.started_at_monotonic,
    )

    # Middleware: last added runs first, so ordering below yields
    # logging/metrics (outermost) -> size limit -> router.
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(RequestContextMiddleware, metrics=metrics)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> Response:
        """Count ingestion validation rejections, then defer to the default 422."""
        if request.url.path.startswith("/api/v1/events"):
            metrics.events_ingestion_failures_total.labels(reason="validation_error").inc()
        return await request_validation_exception_handler(request, exc)

    app.include_router(health_router)
    app.include_router(monitor_router)
    app.include_router(prometheus_router)
    for router in v1_routers:
        app.include_router(router)

    # M004 PR3: same-origin SPA serving. Mounted after every router so route
    # precedence is structural (Starlette matches in registration order) —
    # /api/*, /health, /metrics, /monitor always win. No-op without a build.
    mount_frontend(app, resolve_dist_dir(settings.frontend_dist_dir))
    return app


def build_app() -> FastAPI:
    """Production entry point: ``uvicorn --factory app.main:build_app``.

    Fail-fast configuration validation (M003.5 §2): a misconfigured
    deployment prints one clear, secret-free error and exits with status 2
    before uvicorn binds the listen socket. The systemd unit
    (deploy/systemd/observatory-backend.service) uses this factory.
    """
    try:
        return create_app()
    except ConfigurationError as exc:
        print(f"observatory-backend: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
