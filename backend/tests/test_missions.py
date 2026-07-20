"""Mission tracking tests (M003 §4): lifecycle, transitions, duration, API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.models.mission import MISSION_STATES, is_valid_transition
from tests.conftest import auth_headers

T0 = datetime(2026, 7, 20, 8, 0, 0, tzinfo=UTC)


def _update(state: str, at: datetime, **payload_overrides) -> dict:
    payload = {
        "mission_id": "M003",
        "title": "Observatory Self-Awareness",
        "state": state,
        "assigned_agent": "A001",
    }
    payload.update(payload_overrides)
    return {
        "collector_id": "A001",
        "timestamp": at.isoformat(),
        "event_type": "mission_update",
        "schema_version": 1,
        "payload": payload,
    }


def _post(client: TestClient, body: dict):
    return client.post("/api/v1/events", json=body, headers=auth_headers("test-key-a001"))


def test_transition_rules() -> None:
    assert MISSION_STATES == (
        "Created", "Queued", "Assigned", "Running", "Review", "Completed",
    )
    assert is_valid_transition(None, "Created")
    assert is_valid_transition("Created", "Queued")
    assert is_valid_transition("Created", "Assigned")  # forward jumps allowed
    assert is_valid_transition("Running", "Running")  # idempotent refresh
    assert not is_valid_transition("Review", "Running")  # never backwards
    assert not is_valid_transition("Completed", "Created")
    assert not is_valid_transition("Created", "Exploded")


def test_full_lifecycle_with_duration(client: TestClient) -> None:
    states_and_times = [
        ("Created", T0),
        ("Queued", T0 + timedelta(minutes=1)),
        ("Assigned", T0 + timedelta(minutes=5)),
        ("Running", T0 + timedelta(minutes=10)),
        ("Review", T0 + timedelta(hours=2)),
        ("Completed", T0 + timedelta(hours=3)),
    ]
    for state, at in states_and_times:
        extra = {}
        if state == "Review":
            extra = {"pr_ref": "cht35me/openclaw-observatory#3"}
        if state == "Completed":
            extra = {"commit_sha": "abc1234"}
        response = _post(client, _update(state, at, **extra))
        assert response.status_code == 202, (state, response.text)

    mission = client.get("/api/v1/missions/M003", headers=auth_headers()).json()
    assert mission["state"] == "Completed"
    assert mission["assigned_agent"] == "A001"
    assert mission["created_at"].startswith("2026-07-20T08:00:00")
    assert mission["started_at"].startswith("2026-07-20T08:10:00")
    assert mission["completed_at"].startswith("2026-07-20T11:00:00")
    # Duration = Running -> Completed = 2h50m.
    assert mission["duration_seconds"] == 10200.0
    # Metadata gathered along the way is preserved.
    assert mission["pr_ref"] == "cht35me/openclaw-observatory#3"
    assert mission["commit_sha"] == "abc1234"


def test_backward_transition_rejected(client: TestClient) -> None:
    assert _post(client, _update("Review", T0)).status_code == 202
    response = _post(client, _update("Running", T0 + timedelta(minutes=1)))
    assert response.status_code == 409
    assert "Illegal mission transition" in response.json()["detail"]

    # The projection kept the last valid state.
    mission = client.get("/api/v1/missions/M003", headers=auth_headers()).json()
    assert mission["state"] == "Review"


def test_invalid_mission_payload_rejected(client: TestClient) -> None:
    bad_id = _update("Created", T0)
    bad_id["payload"]["mission_id"] = "mission-3"
    assert _post(client, bad_id).status_code == 422

    bad_state = _update("Exploded", T0)
    assert _post(client, bad_state).status_code == 409

    extra_field = _update("Created", T0)
    extra_field["payload"]["surprise"] = 1
    assert _post(client, extra_field).status_code == 422


def test_transitions_visible_as_events(client: TestClient, storage) -> None:
    """Mission transitions are recorded as events (audit trail)."""
    import asyncio

    assert _post(client, _update("Created", T0)).status_code == 202
    assert _post(client, _update("Running", T0 + timedelta(minutes=1))).status_code == 202

    events = asyncio.run(storage.query_events(event_type="mission_update", limit=10))
    assert len(events) == 2
    assert {event.payload["state"] for event in events} == {"Created", "Running"}


def test_missions_list_and_404(client: TestClient) -> None:
    assert client.get("/api/v1/missions", headers=auth_headers()).json() == []
    assert (
        client.get("/api/v1/missions/M999", headers=auth_headers()).status_code == 404
    )

    _post(client, _update("Created", T0))
    listing = client.get("/api/v1/missions", headers=auth_headers()).json()
    assert len(listing) == 1
    assert listing[0]["mission_id"] == "M003"
    assert listing[0]["duration_seconds"] is None
