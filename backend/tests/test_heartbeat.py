"""Heartbeat processing tests (M003 §5): validation, identity, metrics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry

from tests.conftest import auth_headers


def _heartbeat(collector_id: str = "RPSG01", **overrides) -> dict:
    payload = {
        "collector_type": "raspberry",
        "collector_version": "1.0.0",
        "software_version": "test",
        "failures_total": 0,
    }
    payload.update(overrides.pop("payload", {}))
    body = {
        "collector_id": collector_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "event_type": "heartbeat",
        "schema_version": 1,
        "payload": payload,
    }
    body.update(overrides)
    return body


def _sample(registry: CollectorRegistry, name: str, labels: dict) -> float | None:
    return registry.get_sample_value(name, labels)


def test_valid_heartbeat_accepted_and_measured(client: TestClient) -> None:
    response = client.post(
        "/api/v1/events", json=_heartbeat(), headers=auth_headers("test-key-rpsg01")
    )
    assert response.status_code == 202

    registry = client.app.state.metrics.registry
    assert (
        _sample(
            registry,
            "observatory_heartbeats_received_total",
            {"collector_id": "RPSG01", "collector_type": "raspberry"},
        )
        == 1.0
    )
    assert (
        _sample(
            registry,
            "observatory_heartbeat_latency_seconds_count",
            {"collector_id": "RPSG01"},
        )
        == 1.0
    )


def test_heartbeat_reports_collector_failures_gauge(client: TestClient) -> None:
    body = _heartbeat(payload={"failures_total": 7})
    response = client.post(
        "/api/v1/events", json=body, headers=auth_headers("test-key-rpsg01")
    )
    assert response.status_code == 202
    assert (
        _sample(
            client.app.state.metrics.registry,
            "observatory_collector_reported_failures",
            {"collector_id": "RPSG01"},
        )
        == 7.0
    )


def test_malformed_heartbeat_rejected(client: TestClient) -> None:
    """Strict payload schema: unknown/missing fields are 422 (validated telemetry)."""
    missing = _heartbeat(payload={})
    del missing["payload"]["collector_type"]
    del missing["payload"]["collector_version"]
    response = client.post(
        "/api/v1/events", json=missing, headers=auth_headers("test-key-rpsg01")
    )
    assert response.status_code == 422

    extra = _heartbeat(payload={"surprise": True})
    response = client.post(
        "/api/v1/events", json=extra, headers=auth_headers("test-key-rpsg01")
    )
    assert response.status_code == 422


def test_heartbeat_future_timestamp_rejected(client: TestClient) -> None:
    """Replay protection: forged future timestamps cannot fake liveness."""
    body = _heartbeat(
        timestamp=(datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    )
    response = client.post(
        "/api/v1/events", json=body, headers=auth_headers("test-key-rpsg01")
    )
    assert response.status_code == 422


def test_heartbeat_for_unregistered_identity_rejected(client: TestClient) -> None:
    """Registry is the source of truth: unknown fleet identities are refused.

    'demo' holds a valid API key (SD-017) but is not a Fleet Registry asset;
    heartbeats can never create identities.
    """
    response = client.post(
        "/api/v1/events",
        json=_heartbeat(collector_id="demo"),
        headers=auth_headers("test-key-alpha"),
    )
    assert response.status_code == 403

    # ... and nothing appeared in the registry.
    assert (
        client.get("/api/v1/fleet/demo", headers=auth_headers()).status_code == 404
    )


def test_heartbeat_identity_spoofing_rejected(client: TestClient) -> None:
    """SD-017: a key bound to A001 cannot heartbeat as RPSG01."""
    response = client.post(
        "/api/v1/events",
        json=_heartbeat(collector_id="RPSG01"),
        headers=auth_headers("test-key-a001"),
    )
    assert response.status_code == 403
