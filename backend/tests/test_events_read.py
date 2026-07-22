"""Tests for GET /api/v1/events (M004 PR3 additive read route).

The read side of the event stream feeds the frontend Events timeline
(mission §6): recent events newest-first, exact-match filters, bounded
limit. Reads require authentication like every other v1 endpoint — the
event stream is never anonymous (docs/security.md §3).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.storage.memory import InMemoryEventStorage
from tests.conftest import VALID_EVENT, auth_headers


def _submit(client: TestClient, *, event_type: str, collector_id: str = "demo") -> None:
    body = {
        **VALID_EVENT,
        "collector_id": collector_id,
        "event_type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    key = "test-key-alpha" if collector_id == "demo" else "test-key-beta"
    response = client.post("/api/v1/events", json=body, headers=auth_headers(key))
    assert response.status_code == 202


def test_events_read_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/events").status_code == 401
    assert client.get("/api/v1/events", headers={"X-API-Key": "wrong"}).status_code == 401


def test_events_read_returns_newest_first(client: TestClient) -> None:
    _submit(client, event_type="first")
    _submit(client, event_type="second")
    _submit(client, event_type="third")

    response = client.get("/api/v1/events", headers=auth_headers())
    assert response.status_code == 200
    events = response.json()
    # The app records its own service_start at startup; submitted telemetry
    # must come back newest-first ahead of it.
    types = [event["event_type"] for event in events]
    assert types[:3] == ["third", "second", "first"]
    received = [event["received_at"] for event in events]
    assert received == sorted(received, reverse=True)


def test_events_read_returns_full_event_contract(client: TestClient) -> None:
    _submit(client, event_type="synthetic")
    response = client.get(
        "/api/v1/events", params={"event_type": "synthetic"}, headers=auth_headers()
    )
    assert response.status_code == 200
    (event,) = response.json()
    assert event["collector_id"] == "demo"
    assert event["event_type"] == "synthetic"
    assert event["payload"] == VALID_EVENT["payload"]
    assert event["schema_version"] == 1
    assert "id" in event and "timestamp" in event and "received_at" in event


def test_events_read_filters_by_collector_and_type(client: TestClient) -> None:
    _submit(client, event_type="alpha", collector_id="demo")
    _submit(client, event_type="beta", collector_id="other-collector")

    by_collector = client.get(
        "/api/v1/events", params={"collector_id": "other-collector"}, headers=auth_headers()
    ).json()
    assert {event["collector_id"] for event in by_collector} == {"other-collector"}

    by_type = client.get(
        "/api/v1/events", params={"event_type": "alpha"}, headers=auth_headers()
    ).json()
    assert [event["event_type"] for event in by_type] == ["alpha"]

    combined = client.get(
        "/api/v1/events",
        params={"collector_id": "demo", "event_type": "beta"},
        headers=auth_headers(),
    ).json()
    assert combined == []  # exact-match filters, unknown combination is empty — not an error


def test_events_read_unknown_filter_yields_empty_list(client: TestClient) -> None:
    response = client.get(
        "/api/v1/events", params={"event_type": "never-heard-of-it"}, headers=auth_headers()
    )
    assert response.status_code == 200
    assert response.json() == []


def test_events_read_limit_is_applied(client: TestClient) -> None:
    for _ in range(5):
        _submit(client, event_type="bulk")
    response = client.get(
        "/api/v1/events", params={"event_type": "bulk", "limit": 2}, headers=auth_headers()
    )
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_events_read_limit_bounds_enforced(client: TestClient) -> None:
    """One bounded query, never an unbounded scan: 1 ≤ limit ≤ 500."""
    for bad in (0, -1, 501, 10_000):
        response = client.get("/api/v1/events", params={"limit": bad}, headers=auth_headers())
        assert response.status_code == 422, bad
    ok = client.get("/api/v1/events", params={"limit": 500}, headers=auth_headers())
    assert ok.status_code == 200


def test_events_read_storage_failure_returns_503(
    client: TestClient, storage: InMemoryEventStorage
) -> None:
    storage.fail = True
    response = client.get("/api/v1/events", headers=auth_headers())
    assert response.status_code == 503
    assert "detail" in response.json()


def test_events_read_survives_old_timestamps(client: TestClient) -> None:
    """Ordering is by ingestion time; a stale source timestamp must not break reads."""
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    body = {**VALID_EVENT, "event_type": "stale", "timestamp": old}
    assert client.post("/api/v1/events", json=body, headers=auth_headers()).status_code == 202
    response = client.get("/api/v1/events", headers=auth_headers())
    assert response.status_code == 200
    assert response.json()[0]["event_type"] == "stale"
