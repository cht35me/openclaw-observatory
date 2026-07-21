"""Tests for GET /metrics and metric side-effects of requests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.storage.memory import InMemoryEventStorage
from tests.conftest import VALID_EVENT, auth_headers


def test_metrics_endpoint_exposes_prometheus_format(client: TestClient) -> None:
    client.get("/health")  # generate at least one request metric
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "observatory_http_requests_total" in body
    assert "observatory_http_request_duration_seconds" in body
    assert 'observatory_app_info{version="0.0.0-test"} 1.0' in body


def test_ingestion_success_metric(client: TestClient) -> None:
    client.post("/api/v1/events", json=VALID_EVENT, headers=auth_headers())
    body = client.get("/metrics").text
    assert (
        'observatory_events_ingested_total{collector_id="demo",event_type="synthetic"} 1.0' in body
    )


def test_ingestion_validation_failure_metric(client: TestClient) -> None:
    bad = {**VALID_EVENT, "timestamp": "nonsense"}
    client.post("/api/v1/events", json=bad, headers=auth_headers())
    body = client.get("/metrics").text
    assert 'observatory_events_ingestion_failures_total{reason="validation_error"} 1.0' in body


def test_ingestion_storage_failure_metric(
    client: TestClient, storage: InMemoryEventStorage
) -> None:
    storage.fail = True
    client.post("/api/v1/events", json=VALID_EVENT, headers=auth_headers())
    body = client.get("/metrics").text
    assert 'observatory_events_ingestion_failures_total{reason="storage_error"} 1.0' in body


def test_request_metrics_use_route_template(client: TestClient) -> None:
    client.post("/api/v1/events", json=VALID_EVENT, headers=auth_headers())
    body = client.get("/metrics").text
    assert 'path="/api/v1/events"' in body
