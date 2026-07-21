"""Raspberry Pi host collector assembly (Mission M003 §2/§10, M003.5 §3).

Produces four event kinds on the shared event model (no backend changes
needed for future collectors):

* ``heartbeat`` — liveness + versioning (emitted by the shared runner);
* ``system_metrics`` — CPU/temperature/RAM/disk/load/uptime/network
  (payload shape consumed by the backend health score, M003 §9);
* ``docker_status`` — daemon/container telemetry (M003 §10), extended with
  network mode, per-container uptime, and RX/TX byte counters (M003.5);
* ``host_inventory`` — Host Inventory (M003.5 §3): hardware identity, OS
  identity, structured storage inventory, interfaces, maintenance status.
  Sent on start, when the durable identity changes, and at
  ``INVENTORY_INTERVAL`` (default hourly) — identity is slow-moving and
  does not belong in the 30-second telemetry stream.
"""

from __future__ import annotations

import argparse
import logging
import platform
import time
from collections.abc import Callable
from typing import Any

from observatory_collectors.client import ObservatoryClient
from observatory_collectors.config import CollectorConfig
from observatory_collectors.host_pi import docker_stats, inventory, metrics
from observatory_collectors.runner import CollectorRunner, EventTuple, Task

COLLECTOR_TYPE = "raspberry"

#: Payload schema versions, bumped when a payload shape changes (M003 §1
#: collector versioning: makes rolling upgrades observable).
SYSTEM_METRICS_SCHEMA = 1
#: v2 (M003.5): adds network mode/names, per-container uptime, RX/TX bytes.
DOCKER_STATUS_SCHEMA = 2
HOST_INVENTORY_SCHEMA = 1


def software_version() -> str | None:
    """Host OS identity, e.g. ``Linux 6.18.34+rpt-rpi-v8``."""
    try:
        return f"{platform.system()} {platform.release()}"
    except Exception:  # pragma: no cover - platform never fails on Linux
        return None


class HostTelemetry:
    """Stateful system_metrics producer (CPU% needs two /proc/stat samples)."""

    def __init__(self, sample_delay: float = 0.5) -> None:
        self._previous_cpu = metrics.read_cpu_sample()
        self._sample_delay = sample_delay

    def produce(self) -> list[EventTuple]:
        current_cpu = metrics.read_cpu_sample()
        if self._previous_cpu is None or self._previous_cpu == current_cpu:
            # First run (or clock oddity): take a short synchronous sample.
            self._previous_cpu = current_cpu
            time.sleep(self._sample_delay)
            current_cpu = metrics.read_cpu_sample()
        cpu_percent = metrics.cpu_percent_from_samples(self._previous_cpu, current_cpu)
        self._previous_cpu = current_cpu

        load = metrics.read_load_avg()
        payload: dict[str, Any] = {
            "cpu": {
                "utilization_percent": cpu_percent,
                "temperature_c": metrics.read_cpu_temperature(),
                "load_avg_1m": load[0] if load else None,
                "load_avg_5m": load[1] if load else None,
                "load_avg_15m": load[2] if load else None,
            },
            "memory": metrics.read_memory(),
            "disk": metrics.read_disk("/"),
            "uptime_seconds": metrics.read_uptime(),
            "network": metrics.read_network(),
        }
        return [("system_metrics", payload, SYSTEM_METRICS_SCHEMA)]


def produce_docker() -> list[EventTuple]:
    return [("docker_status", docker_stats.collect(), DOCKER_STATUS_SCHEMA)]


class InventoryTelemetry:
    """host_inventory producer: on start, on durable change, and hourly.

    The producer is scheduled at the fast telemetry interval but only *emits*
    when due: the first run, when the identity signature changes (a disk or
    interface appeared, a kernel booted, …), or when ``inventory_interval``
    elapsed. The signature check uses only cheap file reads; the maintenance
    section (which shells out to read-only ``apt list --upgradable``) is
    gathered only when an event is actually emitted.
    """

    def __init__(
        self,
        interval: float,
        now_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._interval = interval
        self._now = now_fn
        self._last_sent: float | None = None
        self._last_signature: str | None = None

    def produce(self) -> list[EventTuple]:
        now = self._now()
        payload = inventory.collect_identity()
        signature = inventory.stable_signature(payload)
        due = self._last_sent is None or (now - self._last_sent) >= self._interval
        if not due and signature == self._last_signature:
            return []
        payload["maintenance"] = inventory.read_maintenance()
        self._last_sent = now
        self._last_signature = signature
        return [("host_inventory", payload, HOST_INVENTORY_SCHEMA)]


def build_runner(config: CollectorConfig) -> CollectorRunner:
    client = ObservatoryClient(config)
    telemetry = HostTelemetry()
    inventory_telemetry = InventoryTelemetry(config.inventory_interval)
    tasks = [
        Task("system_metrics", config.telemetry_interval, telemetry.produce),
        Task("docker_status", config.telemetry_interval, produce_docker),
        # Scheduled fast, emits slow: the producer applies change detection
        # and the inventory_interval cadence itself.
        Task("host_inventory", config.telemetry_interval, inventory_telemetry.produce),
    ]
    return CollectorRunner(
        config,
        client,
        tasks,
        collector_type=COLLECTOR_TYPE,
        software_version_fn=software_version,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Observatory Raspberry Pi collector")
    parser.add_argument("--once", action="store_true", help="run all tasks once and exit")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = CollectorConfig.from_env(default_collector_name="host-pi")
    runner = build_runner(config)
    if args.once:
        submitted = runner.run_once()
        logging.getLogger("collector").info("submitted %d event(s)", submitted)
        return 0 if submitted > 0 else 1
    runner.run_forever()
    return 0  # pragma: no cover - run_forever does not return
