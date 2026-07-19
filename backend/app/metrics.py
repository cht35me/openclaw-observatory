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
        return cls(
            registry=registry,
            http_requests_total=http_requests_total,
            http_request_duration_seconds=http_request_duration_seconds,
            events_ingested_total=events_ingested_total,
            events_ingestion_failures_total=events_ingestion_failures_total,
            db_latency_seconds=db_latency_seconds,
            app_info=app_info,
        )

    def observe_db_latency(self, operation: str, seconds: float) -> None:
        """Record one database operation's latency (storage-layer hook)."""
        self.db_latency_seconds.labels(operation=operation).observe(seconds)
