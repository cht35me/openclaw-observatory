"""Raspberry Pi host collector assembly (Mission M003 §2/§10).

Produces three event kinds on the shared event model (no backend changes
needed for future collectors):

* ``heartbeat`` — liveness + versioning (emitted by the shared runner);
* ``system_metrics`` — CPU/temperature/RAM/disk/load/uptime/network
  (payload shape consumed by the backend health score, M003 §9);
* ``docker_status`` — daemon/container telemetry (M003 §10).
"""

from __future__ import annotations

import argparse
import logging
import platform
import time
from typing import Any

from observatory_collectors.client import ObservatoryClient
from observatory_collectors.config import CollectorConfig
from observatory_collectors.host_pi import docker_stats, metrics
from observatory_collectors.runner import CollectorRunner, EventTuple, Task

COLLECTOR_TYPE = "raspberry"

#: Payload schema versions, bumped when a payload shape changes (M003 §1
#: collector versioning: makes rolling upgrades observable).
SYSTEM_METRICS_SCHEMA = 1
DOCKER_STATUS_SCHEMA = 1


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


def build_runner(config: CollectorConfig) -> CollectorRunner:
    client = ObservatoryClient(config)
    telemetry = HostTelemetry()
    tasks = [
        Task("system_metrics", config.telemetry_interval, telemetry.produce),
        Task("docker_status", config.telemetry_interval, produce_docker),
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
