"""Tests for GET /health."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.storage.memory import InMemoryEventStorage


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.0.0-test"
    assert body["uptime_seconds"] >= 0
    assert body["database"] == {"connected": True}


def test_health_requires_no_auth(client: TestClient) -> None:
    """Health is an unauthenticated probe endpoint (see OPEN_QUESTIONS.md)."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_degraded_when_database_unreachable(
    client: TestClient, storage: InMemoryEventStorage
) -> None:
    """Database outage: still HTTP 200, but status flips to degraded."""
    storage.fail = True
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == {"connected": False}


def test_health_includes_request_id_header(client: TestClient) -> None:
    response = client.get("/health")
    assert "x-request-id" in response.headers
    assert len(response.headers["x-request-id"]) == 32
