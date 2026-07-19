"""Tests for structured request logging."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.logging import JsonFormatter
from tests.conftest import VALID_EVENT, auth_headers


def test_request_log_contains_required_fields(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="observatory.request"):
        client.get("/health")
    records = [r for r in caplog.records if r.name == "observatory.request"]
    assert records, "expected one structured request log entry"
    record = records[-1]
    assert len(record.request_id) == 32
    assert record.endpoint == "/health"
    assert record.status == 200
    assert record.duration_ms >= 0
    assert record.method == "GET"


def test_request_log_includes_collector_id_for_ingestion(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="observatory.request"):
        client.post("/api/v1/events", json=VALID_EVENT, headers=auth_headers())
    records = [r for r in caplog.records if r.name == "observatory.request"]
    assert records[-1].collector_id == "demo"


def test_request_log_never_contains_api_key(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    formatter = JsonFormatter()
    with caplog.at_level(logging.DEBUG):
        client.post("/api/v1/events", json=VALID_EVENT, headers=auth_headers())
    for record in caplog.records:
        assert "test-key-alpha" not in formatter.format(record)


def test_json_formatter_emits_valid_json(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("observatory.test")
    with caplog.at_level(logging.INFO, logger="observatory.test"):
        logger.info("hello", extra={"request_id": "abc123", "status": 200})
    entry = json.loads(JsonFormatter().format(caplog.records[-1]))
    assert entry["message"] == "hello"
    assert entry["request_id"] == "abc123"
    assert entry["status"] == 200
    assert entry["level"] == "INFO"
    assert "timestamp" in entry
