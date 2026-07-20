"""Runner tests: scheduling, heartbeat payload, failure accounting."""

from __future__ import annotations

from observatory_collectors.config import CollectorConfig
from observatory_collectors.runner import CollectorRunner, Task
from observatory_collectors import __version__

CONFIG = CollectorConfig.from_env(
    {
        "OBSERVATORY_URL": "http://obs.example:8000",
        "OBSERVATORY_API_KEY": "test-key",
        "FLEET_ID": "RPSG01",
        "HEARTBEAT_INTERVAL": "30",
        "TELEMETRY_INTERVAL": "60",
    }
)


class FakeClient:
    def __init__(self, accept: bool = True) -> None:
        self.accept = accept
        self.failures_total = 0
        self.submitted: list[tuple[str, dict, int]] = []

    def submit_event(self, event_type, payload, schema_version=1, timestamp=None):
        if not self.accept:
            self.failures_total += 1
            return False
        self.submitted.append((event_type, payload, schema_version))
        return True


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _runner(client: FakeClient, clock: FakeClock, tasks=None) -> CollectorRunner:
    return CollectorRunner(
        CONFIG,
        client,  # type: ignore[arg-type]
        tasks or [],
        collector_type="raspberry",
        software_version_fn=lambda: "test-os 1.0",
        now_fn=clock,
        sleep_fn=lambda s: None,
    )


def test_heartbeat_payload_contents() -> None:
    client, clock = FakeClient(), FakeClock()
    runner = _runner(client, clock)
    clock.now += 12.0
    assert runner.run_pending() == 1

    event_type, payload, schema = client.submitted[0]
    assert event_type == "heartbeat"
    assert schema == 1
    assert payload["collector_type"] == "raspberry"
    assert payload["collector_version"] == __version__
    assert payload["software_version"] == "test-os 1.0"
    assert payload["uptime_seconds"] == 12.0
    assert payload["failures_total"] == 0


def test_tasks_respect_their_intervals() -> None:
    client, clock = FakeClient(), FakeClock()
    produced = []
    task = Task("metrics", 60.0, lambda: produced.append(1) or [("system_metrics", {}, 1)])
    runner = _runner(client, clock, tasks=[task])

    runner.run_pending()  # both due immediately
    assert len(produced) == 1
    clock.now += 30.0  # heartbeat due again (30s), metrics not (60s)
    runner.run_pending()
    heartbeats = [e for e in client.submitted if e[0] == "heartbeat"]
    metrics = [e for e in client.submitted if e[0] == "system_metrics"]
    assert len(heartbeats) == 2
    assert len(metrics) == 1
    clock.now += 30.0
    runner.run_pending()
    assert len([e for e in client.submitted if e[0] == "system_metrics"]) == 2


def test_producer_crash_counted_and_reported() -> None:
    client, clock = FakeClient(), FakeClock()

    def broken():
        raise RuntimeError("sensor exploded")

    runner = _runner(client, clock, tasks=[Task("broken", 30.0, broken)])
    runner.run_pending()
    assert runner.collection_failures == 1

    # The next heartbeat self-reports the failure.
    clock.now += 30.0
    runner.run_pending()
    last_heartbeat = [e for e in client.submitted if e[0] == "heartbeat"][-1]
    assert last_heartbeat[1]["failures_total"] == 1


def test_run_once_forces_all_tasks() -> None:
    client, clock = FakeClient(), FakeClock()
    task = Task("metrics", 3600.0, lambda: [("system_metrics", {}, 1)])
    runner = _runner(client, clock, tasks=[task])
    assert runner.run_once() == 2  # heartbeat + metrics
    assert runner.run_once() == 2  # forced again despite intervals
