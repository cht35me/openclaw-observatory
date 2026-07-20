"""Prometheus metrics (Mission M002 scope).

A fresh :class:`~prometheus_client.CollectorRegistry` is created per
application instance (instead of the process-global default registry) so the
app factory stays re-entrant — required for isolated tests and safe for
multi-app processes.
"""

from __future__ import annotations

from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


@dataclass(frozen=True)
class AppMetrics:
    """Container for all application metrics and their registry."""

    registry: CollectorRegistry
    http_requests_total: Counter
    http_request_duration_seconds: Histogram
    events_ingested_total: Counter
    events_ingestion_failures_total: Counter
    db_latency_seconds: Histogram
    app_info: Gauge
    # --- Fleet / heartbeat metrics (Mission M003) ---
    fleet_registered_assets: Gauge
    fleet_active_assets: Gauge
    fleet_offline_assets: Gauge
    fleet_unknown_assets: Gauge
    heartbeats_received_total: Counter
    heartbeat_latency_seconds: Histogram
    collector_reported_failures: Gauge
    offline_transitions_total: Counter

    @classmethod
    def create(cls, version: str) -> AppMetrics:
        """Build a metrics set bound to a new registry.

        The ``path`` label always carries the *route template* (e.g.
        ``/api/v1/events``), never raw URLs, to keep label cardinality bounded.
        """
        registry = CollectorRegistry()
        http_requests_total = Counter(
            "observatory_http_requests_total",
            "Total HTTP requests processed.",
            labelnames=("method", "path", "status"),
            registry=registry,
        )
        http_request_duration_seconds = Histogram(
            "observatory_http_request_duration_seconds",
            "HTTP request latency in seconds.",
            labelnames=("method", "path"),
            registry=registry,
        )
        events_ingested_total = Counter(
            "observatory_events_ingested_total",
            "Telemetry events successfully ingested.",
            labelnames=("collector_id", "event_type"),
            registry=registry,
        )
        events_ingestion_failures_total = Counter(
            "observatory_events_ingestion_failures_total",
            "Telemetry events rejected or failed to persist.",
            labelnames=("reason",),
            registry=registry,
        )
        db_latency_seconds = Histogram(
            "observatory_db_latency_seconds",
            "Database operation latency in seconds.",
            labelnames=("operation",),
            registry=registry,
        )
        app_info = Gauge(
            "observatory_app_info",
            "Static application metadata (value is always 1).",
            labelnames=("version",),
            registry=registry,
        )
        app_info.labels(version=version).set(1)
        fleet_registered_assets = Gauge(
            "observatory_fleet_registered_assets",
            "Assets present in the Fleet Registry.",
            registry=registry,
        )
        fleet_active_assets = Gauge(
            "observatory_fleet_active_assets",
            "Registry assets currently online (fresh heartbeat).",
            registry=registry,
        )
        fleet_offline_assets = Gauge(
            "observatory_fleet_offline_assets",
            "Registry assets whose newest heartbeat exceeded OFFLINE_TIMEOUT.",
            registry=registry,
        )
        fleet_unknown_assets = Gauge(
            "observatory_fleet_unknown_assets",
            "Registry assets that have never sent a heartbeat.",
            registry=registry,
        )
        heartbeats_received_total = Counter(
            "observatory_heartbeats_received_total",
            "Heartbeat events accepted, by collector identity and type.",
            labelnames=("collector_id", "collector_type"),
            registry=registry,
        )
        heartbeat_latency_seconds = Histogram(
            "observatory_heartbeat_latency_seconds",
            "Delay between heartbeat source timestamp and ingestion.",
            labelnames=("collector_id",),
            registry=registry,
        )
        collector_reported_failures = Gauge(
            "observatory_collector_reported_failures",
            "Cumulative failure count self-reported in a collector's newest heartbeat.",
            labelnames=("collector_id",),
            registry=registry,
        )
        offline_transitions_total = Counter(
            "observatory_offline_transitions_total",
            "Connectivity transitions detected (direction: offline|online).",
            labelnames=("collector_id", "direction"),
            registry=registry,
        )
        return cls(
            registry=registry,
            http_requests_total=http_requests_total,
            http_request_duration_seconds=http_request_duration_seconds,
            events_ingested_total=events_ingested_total,
            events_ingestion_failures_total=events_ingestion_failures_total,
            db_latency_seconds=db_latency_seconds,
            app_info=app_info,
            fleet_registered_assets=fleet_registered_assets,
            fleet_active_assets=fleet_active_assets,
            fleet_offline_assets=fleet_offline_assets,
            fleet_unknown_assets=fleet_unknown_assets,
            heartbeats_received_total=heartbeats_received_total,
            heartbeat_latency_seconds=heartbeat_latency_seconds,
            collector_reported_failures=collector_reported_failures,
            offline_transitions_total=offline_transitions_total,
        )

    def observe_db_latency(self, operation: str, seconds: float) -> None:
        """Record one database operation's latency (storage-layer hook)."""
        self.db_latency_seconds.labels(operation=operation).observe(seconds)
