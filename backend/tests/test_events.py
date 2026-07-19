"""Tests for POST /api/v1/events: validation, persistence, failure paths."""

from __future__ import annotations

from datetime import UTC
from uuid import UUID

from fastapi.testclient import TestClient

from app.storage.memory import InMemoryEventStorage
from tests.conftest import VALID_EVENT, auth_headers


def test_valid_event_accepted(client: TestClient) -> None:
    response = client.post("/api/v1/events", json=VALID_EVENT, headers=auth_headers())
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    UUID(body["id"])  # must be a valid UUID
    assert "received_at" in body


def test_event_persisted_with_canonical_fields(
    client: TestClient, storage: InMemoryEventStorage
) -> None:
    response = client.post("/api/v1/events", json=VALID_EVENT, headers=auth_headers())
    assert response.status_code == 202

    stored = client.portal.call(storage.query_events)
    assert len(stored) == 1
    event = stored[0]
    assert str(event.id) == response.json()["id"]
    assert event.collector_id == "demo"
    assert event.event_type == "synthetic"
    assert event.payload == {"temperature": 41, "status": "ok"}
    assert event.schema_version == 1
    assert event.timestamp.tzinfo is not None
    assert event.timestamp.astimezone(UTC).isoformat() == "2026-07-19T12:00:00+00:00"
    assert event.received_at.tzinfo is not None


def test_schema_version_can_be_supplied(client: TestClient, storage: InMemoryEventStorage) -> None:
    payload = {**VALID_EVENT, "schema_version": 3}
    response = client.post("/api/v1/events", json=payload, headers=auth_headers())
    assert response.status_code == 202
    stored = client.portal.call(storage.query_events)
    assert stored[0].schema_version == 3


def test_unknown_field_rejected(client: TestClient) -> None:
    payload = {**VALID_EVENT, "surprise": True}
    response = client.post("/api/v1/events", json=payload, headers=auth_headers())
    assert response.status_code == 422


def test_missing_required_field_rejected(client: TestClient) -> None:
    payload = {key: value for key, value in VALID_EVENT.items() if key != "event_type"}
    response = client.post("/api/v1/events", json=payload, headers=auth_headers())
    assert response.status_code == 422


def test_naive_timestamp_rejected(client: TestClient) -> None:
    payload = {**VALID_EVENT, "timestamp": "2026-07-19T12:00:00"}
    response = client.post("/api/v1/events", json=payload, headers=auth_headers())
    assert response.status_code == 422


def test_malformed_collector_id_rejected(client: TestClient) -> None:
    payload = {**VALID_EVENT, "collector_id": "bad id\nwith newline"}
    response = client.post("/api/v1/events", json=payload, headers=auth_headers())
    assert response.status_code == 422


def test_non_object_payload_rejected(client: TestClient) -> None:
    payload = {**VALID_EVENT, "payload": "not-an-object"}
    response = client.post("/api/v1/events", json=payload, headers=auth_headers())
    assert response.status_code == 422


def test_storage_failure_returns_503(
    client: TestClient, storage: InMemoryEventStorage
) -> None:
    storage.fail = True
    response = client.post("/api/v1/events", json=VALID_EVENT, headers=auth_headers())
    assert response.status_code == 503


def test_oversized_body_rejected_with_413(client: TestClient) -> None:
    huge = {**VALID_EVENT, "payload": {"blob": "x" * 10_000}}  # limit is 4096 in tests
    response = client.post("/api/v1/events", json=huge, headers=auth_headers())
    assert response.status_code == 413


def test_validation_failure_does_not_persist(
    client: TestClient, storage: InMemoryEventStorage
) -> None:
    payload = {**VALID_EVENT, "timestamp": "not-a-timestamp"}
    response = client.post("/api/v1/events", json=payload, headers=auth_headers())
    assert response.status_code == 422
    assert client.portal.call(storage.query_events) == []
