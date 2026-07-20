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
from app.storage.memory import (
    InMemoryEventStorage,
    InMemoryMissionStorage,
    InMemoryRegistryStorage,
)

#: Key → identity bindings for the test app (SD-017; never real credentials).
#: demo/other-collector exercise generic ingestion; RPSG01/A001 are seeded
#: Fleet Registry identities used by the M003 heartbeat/mission tests.
TEST_KEY_BINDINGS: dict[str, str] = {
    "test-key-alpha": "demo",
    "test-key-beta": "other-collector",
    "test-key-rpsg01": "RPSG01",
    "test-key-a001": "A001",
}
TEST_API_KEYS = tuple(TEST_KEY_BINDINGS)

VALID_EVENT: dict = {
    "collector_id": "demo",
    "timestamp": "2026-07-19T12:00:00Z",
    "event_type": "synthetic",
    "payload": {"temperature": 41, "status": "ok"},
}


def auth_headers(key: str = TEST_API_KEYS[0]) -> dict[str, str]:
    """Build collector auth headers for a request."""
    return {"X-API-Key": key}


def event_for(collector_id: str) -> dict:
    """A valid event payload for the given collector identity."""
    return {**VALID_EVENT, "collector_id": collector_id}


@pytest.fixture
def settings() -> Settings:
    """Settings isolated from the host environment and any .env file."""
    return Settings(
        _env_file=None,
        api_keys=",".join(
            f"{collector_id}:{key}" for key, collector_id in TEST_KEY_BINDINGS.items()
        ),
        app_version="0.0.0-test",
        log_level="INFO",
        max_request_bytes=4096,
        background_tasks_enabled=False,  # deterministic tests; loops tested directly
    )


@pytest.fixture
def storage() -> InMemoryEventStorage:
    """Fresh in-memory storage backend per test."""
    return InMemoryEventStorage()


@pytest.fixture
def registry_storage() -> InMemoryRegistryStorage:
    """Fresh in-memory Fleet Registry backend per test."""
    return InMemoryRegistryStorage()


@pytest.fixture
def mission_storage() -> InMemoryMissionStorage:
    """Fresh in-memory mission projection backend per test."""
    return InMemoryMissionStorage()


@pytest.fixture
def client(
    settings: Settings,
    storage: InMemoryEventStorage,
    registry_storage: InMemoryRegistryStorage,
    mission_storage: InMemoryMissionStorage,
) -> Iterator[TestClient]:
    """HTTP client against a fully wired app (lifespan running).

    The app seeds the Fleet Registry from :mod:`app.services.seed` during
    startup, so the registry contains A001/RPSG01/OBS01 in every test.
    """
    app = create_app(
        settings=settings,
        storage=storage,
        registry_storage=registry_storage,
        mission_storage=mission_storage,
    )
    with TestClient(app) as test_client:
        yield test_client
