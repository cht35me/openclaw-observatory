"""Shared fixtures: app factory wiring with fake storage and test settings.

The suite runs fully offline: the application under test uses
:class:`InMemoryEventStorage`. ClickHouse-dependent integration tests live in
``test_clickhouse_integration.py`` and skip themselves when no server is
reachable.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.storage.memory import InMemoryEventStorage

#: Keys configured for the test app (never real credentials).
TEST_API_KEYS = ("test-key-alpha", "test-key-beta")

VALID_EVENT: dict = {
    "collector_id": "demo",
    "timestamp": "2026-07-19T12:00:00Z",
    "event_type": "synthetic",
    "payload": {"temperature": 41, "status": "ok"},
}


def auth_headers(key: str = TEST_API_KEYS[0]) -> dict[str, str]:
    """Build collector auth headers for a request."""
    return {"X-API-Key": key}


@pytest.fixture
def settings() -> Settings:
    """Settings isolated from the host environment and any .env file."""
    return Settings(
        _env_file=None,
        api_keys=",".join(TEST_API_KEYS),
        app_version="0.0.0-test",
        log_level="INFO",
        max_request_bytes=4096,
    )


@pytest.fixture
def storage() -> InMemoryEventStorage:
    """Fresh in-memory storage backend per test."""
    return InMemoryEventStorage()


@pytest.fixture
def client(settings: Settings, storage: InMemoryEventStorage) -> Iterator[TestClient]:
    """HTTP client against a fully wired app (lifespan running)."""
    app = create_app(settings=settings, storage=storage)
    with TestClient(app) as test_client:
        yield test_client
