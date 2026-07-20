"""Computed health score (Mission M003 §9).

Instead of a bare online/offline flag, every asset gets a derived health
status — ``Healthy`` / ``Warning`` / ``Critical`` / ``Offline`` — computed
at read time from:

* heartbeat age (via connectivity and a warning ratio),
* CPU temperature,
* disk usage,
* RAM usage,
* collector failure counts (reported cumulatively in heartbeats).

The score is computed by the backend, so future dashboards need no collector
changes; thresholds are configuration (:class:`app.config.Settings`), not
collector logic. Missing signals are ignored rather than penalized — an
agent collector without CPU-temperature data is not "unhealthy", it simply
is not judged on that signal.
"""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.models.registry import Connectivity, HealthStatus


def _get_number(payload: dict[str, Any], *path: str) -> float | None:
    """Fetch a nested numeric value defensively (telemetry is untrusted data)."""
    node: Any = payload
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    if isinstance(node, bool) or not isinstance(node, (int, float)):
        return None
    return float(node)


def compute_health(
    settings: Settings,
    connectivity: Connectivity,
    heartbeat_age_seconds: float | None,
    system_payload: dict[str, Any] | None,
    collector_failures: int | None,
) -> HealthStatus:
    """Derive one asset's health status.

    Args:
        connectivity: heartbeat-derived reachability.
        heartbeat_age_seconds: age of the newest heartbeat (source timestamp).
        system_payload: newest ``system_metrics`` event payload, when any.
        collector_failures: cumulative failures from the newest heartbeat.
    """
    if connectivity is Connectivity.OFFLINE:
        return HealthStatus.OFFLINE
    if connectivity is Connectivity.UNKNOWN:
        return HealthStatus.UNKNOWN

    warning = False

    # Heartbeat age: creeping staleness degrades to Warning before the
    # offline detector's hard cut-off fires.
    if (
        heartbeat_age_seconds is not None
        and heartbeat_age_seconds
        > settings.offline_timeout * settings.health_heartbeat_warning_ratio
    ):
        warning = True

    if collector_failures is not None and (
        collector_failures >= settings.health_collector_failures_warning
    ):
        warning = True

    if system_payload:
        cpu_temp = _get_number(system_payload, "cpu", "temperature_c")
        disk = _get_number(system_payload, "disk", "used_percent")
        ram = _get_number(system_payload, "memory", "used_percent")

        if cpu_temp is not None:
            if cpu_temp >= settings.health_cpu_temp_critical_c:
                return HealthStatus.CRITICAL
            if cpu_temp >= settings.health_cpu_temp_warning_c:
                warning = True
        if disk is not None:
            if disk >= settings.health_disk_critical_percent:
                return HealthStatus.CRITICAL
            if disk >= settings.health_disk_warning_percent:
                warning = True
        if ram is not None:
            if ram >= settings.health_ram_critical_percent:
                return HealthStatus.CRITICAL
            if ram >= settings.health_ram_warning_percent:
                warning = True

    return HealthStatus.WARNING if warning else HealthStatus.HEALTHY
