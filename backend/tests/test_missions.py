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


def test_transition_rules_normal_operation() -> None:
    assert MISSION_STATES == (
        "Created", "Queued", "Assigned", "Running", "Review", "Completed",
    )
    assert is_valid_transition(None, "Created")
    assert is_valid_transition("Created", "Queued")
    assert is_valid_transition("Running", "Running")  # idempotent refresh
    # Normal operation follows the explicit graph — no forward skips.
    assert not is_valid_transition("Created", "Assigned")
    assert not is_valid_transition("Created", "Completed")
    assert not is_valid_transition(None, "Running")  # unknown enters at Created
    assert not is_valid_transition("Review", "Running")  # never backwards
    assert not is_valid_transition("Completed", "Created")
    assert not is_valid_transition("Created", "Exploded")


def test_transition_rules_backfill() -> None:
    """Privileged backfill/recovery: enter at or jump to a later state."""
    assert is_valid_transition(None, "Running", backfill=True)  # import
    assert is_valid_transition(None, "Completed", backfill=True)
    assert is_valid_transition("Created", "Review", backfill=True)  # recovery jump
    assert is_valid_transition("Running", "Running", backfill=True)
    # Regression is never allowed, backfill included.
    assert not is_valid_transition("Review", "Running", backfill=True)
    # Completed stays terminal, backfill included.
    assert not is_valid_transition("Completed", "Running", backfill=True)
    assert is_valid_transition("Completed", "Completed", backfill=True)
    assert not is_valid_transition("Created", "Exploded", backfill=True)


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
    # Entering at Review for an unknown mission needs privileged backfill.
    assert _post(client, _update("Review", T0, backfill=True)).status_code == 202
    response = _post(client, _update("Running", T0 + timedelta(minutes=1)))
    assert response.status_code == 409
    assert "Illegal mission transition" in response.json()["detail"]

    # Regression stays rejected even with the backfill flag.
    response = _post(
        client, _update("Running", T0 + timedelta(minutes=2), backfill=True)
    )
    assert response.status_code == 409

    # The projection kept the last valid state.
    mission = client.get("/api/v1/missions/M003", headers=auth_headers()).json()
    assert mission["state"] == "Review"


def test_forward_skip_requires_backfill(client: TestClient) -> None:
    """Normal operation may not skip states; backfill=true may (audited)."""
    assert _post(client, _update("Created", T0)).status_code == 202

    # Created -> Running skips Queued/Assigned: rejected in normal operation.
    response = _post(client, _update("Running", T0 + timedelta(minutes=1)))
    assert response.status_code == 409
    assert "backfill" in response.json()["detail"]

    # The same jump with the privileged flag is accepted.
    response = _post(
        client, _update("Running", T0 + timedelta(minutes=2), backfill=True)
    )
    assert response.status_code == 202

    mission = client.get("/api/v1/missions/M003", headers=auth_headers()).json()
    assert mission["state"] == "Running"
    assert mission["started_at"].startswith("2026-07-20T08:02:00")


def test_unknown_mission_must_enter_at_created(client: TestClient) -> None:
    response = _post(client, _update("Running", T0))
    assert response.status_code == 409
    assert _post(client, _update("Created", T0)).status_code == 202


def test_completed_terminal_even_with_backfill(client: TestClient) -> None:
    assert _post(client, _update("Completed", T0, backfill=True)).status_code == 202
    response = _post(
        client, _update("Running", T0 + timedelta(minutes=1), backfill=True)
    )
    assert response.status_code == 409
    # Metadata-refresh self-loop remains legal.
    response = _post(
        client,
        _update("Completed", T0 + timedelta(minutes=2), commit_sha="abc1234"),
    )
    assert response.status_code == 202


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
    assert _post(client, _update("Queued", T0 + timedelta(minutes=1))).status_code == 202

    events = asyncio.run(storage.query_events(event_type="mission_update", limit=10))
    assert len(events) == 2
    assert {event.payload["state"] for event in events} == {"Created", "Queued"}


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
