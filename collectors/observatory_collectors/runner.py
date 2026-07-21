"""Collection loop shared by all collectors (Mission M003 §5).

A collector is a set of *tasks* — named callables returning events — plus the
always-present heartbeat task. The runner schedules each task on its own
interval, submits results through :class:`ObservatoryClient`, counts
collection failures, and supports ``--once`` for smoke tests and systemd
``Type=oneshot`` checks.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from observatory_collectors import __version__ as COLLECTORS_VERSION
from observatory_collectors.client import ObservatoryClient
from observatory_collectors.config import CollectorConfig

_logger = logging.getLogger("collector.runner")

#: One produced event: (event_type, payload, schema_version).
EventTuple = tuple[str, dict[str, Any], int]


@dataclass(frozen=True)
class Task:
    """A named telemetry producer scheduled at a fixed interval."""

    name: str
    interval: float
    produce: Callable[[], Iterable[EventTuple]]


class CollectorRunner:
    """Schedules tasks and heartbeats; the shared main loop."""

    def __init__(
        self,
        config: CollectorConfig,
        client: ObservatoryClient,
        tasks: list[Task],
        collector_type: str,
        software_version_fn: Callable[[], str | None] = lambda: None,
        now_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._client = client
        self._collector_type = collector_type
        self._software_version_fn = software_version_fn
        self._now = now_fn
        self._sleep = sleep_fn
        self._started = self._now()
        #: Collection failures (probe crashes), merged into heartbeat totals.
        self.collection_failures = 0

        heartbeat = Task(
            name="heartbeat",
            interval=config.heartbeat_interval,
            produce=self._heartbeat_events,
        )
        self._tasks = [heartbeat, *tasks]
        self._next_run = {task.name: 0.0 for task in self._tasks}

    # ------------------------------------------------------------------ #

    def _heartbeat_events(self) -> list[EventTuple]:
        payload = {
            "collector_type": self._collector_type,
            "collector_version": COLLECTORS_VERSION,
            "software_version": self._software_version_fn(),
            "uptime_seconds": round(self._now() - self._started, 3),
            "failures_total": self._client.failures_total + self.collection_failures,
        }
        if payload["software_version"] is None:
            del payload["software_version"]
        return [("heartbeat", payload, 1)]

    def run_pending(self) -> int:
        """Run every task whose interval elapsed; returns submissions made."""
        submitted = 0
        now = self._now()
        for task in self._tasks:
            if now < self._next_run[task.name]:
                continue
            self._next_run[task.name] = now + task.interval
            try:
                events = list(task.produce())
            except Exception:
                self.collection_failures += 1
                _logger.exception("task %s failed to produce telemetry", task.name)
                continue
            for event_type, payload, schema_version in events:
                if self._client.submit_event(event_type, payload, schema_version):
                    submitted += 1
        return submitted

    def run_once(self) -> int:
        """Force-run all tasks once (smoke tests, ``--once``)."""
        for task in self._tasks:
            self._next_run[task.name] = 0.0
        return self.run_pending()

    def run_forever(self, tick: float = 1.0) -> None:  # pragma: no cover - loop
        _logger.info(
            "collector started: fleet_id=%s type=%s heartbeat=%.0fs",
            self._config.fleet_id, self._collector_type,
            self._config.heartbeat_interval,
        )
        while True:
            self.run_pending()
            self._sleep(tick)
