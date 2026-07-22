"""Tests for GET /api/v1/fleet/{fleet_id}/docker-status (M004 PR3).

A dedicated, allowlisted latest-telemetry read: exactly one event type
(``docker_status``) is served, never a generic event browser. 404 is a
normal condition for assets without docker telemetry — consumers branch on
it, never retry.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.models.telemetry import DOCKER_STATUS_EVENT_TYPE, EXPOSED_TELEMETRY_TYPES
from tests.conftest import auth_headers

DOCKER_PAYLOAD = {
    "daemon_running": True,
    "containers_total": 2,
    "containers_running": 2,
    "containers_failed": 0,
    "restart_count_total": 1,
    "containers": [
        {
            "name": "observatory-backend",
            "status": "running",
            "restart_count": 1,
            "cpu_percent": 1.25,
            "memory_percent": 3.5,
            "network_rx_bytes": 21_000_000,
            "network_tx_bytes": 1_440,
        }
    ],
}


def _submit_docker_status(client: TestClient, payload: dict | None = None) -> str:
    response = client.post(
        "/api/v1/events",
        json={
            "collector_id": "RPSG01",
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": DOCKER_STATUS_EVENT_TYPE,
            "schema_version": 2,
            "payload": payload if payload is not None else DOCKER_PAYLOAD,
        },
        headers=auth_headers("test-key-rpsg01"),
    )
    assert response.status_code == 202
    return response.json()["id"]


def test_docker_status_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/fleet/RPSG01/docker-status").status_code == 401
    assert (
        client.get("/api/v1/fleet/RPSG01/docker-status", headers={"X-API-Key": "bad"}).status_code
        == 401
    )


def test_docker_status_unknown_fleet_id_404(client: TestClient) -> None:
    _submit_docker_status(client)
    response = client.get("/api/v1/fleet/NOPE99/docker-status", headers=auth_headers())
    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown fleet_id."


def test_docker_status_no_data_404(client: TestClient) -> None:
    """A registered asset without docker telemetry is a normal 404, not an error."""
    response = client.get("/api/v1/fleet/A001/docker-status", headers=auth_headers())
    assert response.status_code == 404
    assert "No docker telemetry" in response.json()["detail"]


def test_docker_status_happy_path(client: TestClient) -> None:
    _submit_docker_status(client)
    response = client.get("/api/v1/fleet/RPSG01/docker-status", headers=auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["fleet_id"] == "RPSG01"
    assert body["event_type"] == DOCKER_STATUS_EVENT_TYPE
    assert body["schema_version"] == 2
    assert body["payload"] == DOCKER_PAYLOAD
    # Freshness contract: source timestamp plus ingestion stamp, both present.
    assert body["timestamp"] and body["received_at"]
    datetime.fromisoformat(body["timestamp"])
    datetime.fromisoformat(body["received_at"])


def test_docker_status_returns_newest_event(client: TestClient) -> None:
    _submit_docker_status(client, {"daemon_running": False})
    _submit_docker_status(client, DOCKER_PAYLOAD)
    response = client.get("/api/v1/fleet/RPSG01/docker-status", headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["payload"]["daemon_running"] is True


def test_exposed_telemetry_allowlist_is_docker_only(client: TestClient) -> None:
    """Supervisor-gated contract: the generic event stream stays behind an
    explicit allowlist; today exactly one type is exposed via fleet routes."""
    assert EXPOSED_TELEMETRY_TYPES == (DOCKER_STATUS_EVENT_TYPE,)
