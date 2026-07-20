"""Delivery client tests: retries, backoff, failure accounting."""

from __future__ import annotations

import io
import json
import urllib.error
from contextlib import contextmanager

from observatory_collectors.client import ObservatoryClient
from observatory_collectors.config import CollectorConfig

CONFIG = CollectorConfig.from_env(
    {
        "OBSERVATORY_URL": "http://obs.example:8000",
        "OBSERVATORY_API_KEY": "test-key",
        "FLEET_ID": "RPSG01",
        "MAX_RETRIES": "2",
    }
)


class FakeOpener:
    """Scripted urlopen replacement: pops one outcome per call."""

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[object] = []

    @contextmanager
    def __call__(self, request, timeout=None):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        yield io.BytesIO(b'{"status":"accepted"}')


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://obs", code, "err", {}, io.BytesIO(b""))


def test_successful_submission_sends_identity_and_key() -> None:
    opener = FakeOpener(["ok"])
    client = ObservatoryClient(CONFIG, sleep_fn=lambda s: None, opener=opener)
    assert client.submit_event("heartbeat", {"collector_type": "raspberry",
                                             "collector_version": "1.0.0"}) is True
    assert client.failures_total == 0

    request = opener.requests[0]
    assert request.full_url == "http://obs.example:8000/api/v1/events"
    assert request.get_header("X-api-key") == "test-key"
    body = json.loads(request.data.decode("utf-8"))
    assert body["collector_id"] == "RPSG01"
    assert body["event_type"] == "heartbeat"
    assert "timestamp" in body


def test_transient_errors_retried_then_succeed() -> None:
    sleeps: list[float] = []
    opener = FakeOpener([_http_error(503), OSError("conn refused"), "ok"])
    client = ObservatoryClient(CONFIG, sleep_fn=sleeps.append, opener=opener)
    assert client.submit_event("system_metrics", {}) is True
    assert client.failures_total == 0
    assert sleeps == [1.0, 2.0]  # exponential backoff


def test_client_errors_never_retried() -> None:
    opener = FakeOpener([_http_error(422)])
    client = ObservatoryClient(CONFIG, sleep_fn=lambda s: None, opener=opener)
    assert client.submit_event("heartbeat", {}) is False
    assert client.failures_total == 1
    assert len(opener.requests) == 1  # no retry on 4xx


def test_exhausted_retries_counted_not_raised() -> None:
    opener = FakeOpener([OSError("down")] * 3)  # MAX_RETRIES=2 -> 3 attempts
    client = ObservatoryClient(CONFIG, sleep_fn=lambda s: None, opener=opener)
    assert client.submit_event("heartbeat", {}) is False
    assert client.failures_total == 1
    assert len(opener.requests) == 3
