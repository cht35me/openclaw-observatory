"""Tests for collector API-key authentication."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth import ApiKeyAuthenticator
from app.config import Settings
from app.main import create_app
from app.storage.memory import InMemoryEventStorage
from tests.conftest import TEST_API_KEYS, VALID_EVENT, auth_headers


def test_missing_key_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/events", json=VALID_EVENT)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "ApiKey"


def test_wrong_key_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/events", json=VALID_EVENT, headers=auth_headers("not-a-real-key")
    )
    assert response.status_code == 401


def test_empty_key_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/events", json=VALID_EVENT, headers=auth_headers(""))
    assert response.status_code == 401


def test_valid_key_accepted(client: TestClient) -> None:
    response = client.post("/api/v1/events", json=VALID_EVENT, headers=auth_headers())
    assert response.status_code == 202


def test_every_configured_key_works(client: TestClient) -> None:
    for key in TEST_API_KEYS:
        response = client.post(
            "/api/v1/events", json=VALID_EVENT, headers=auth_headers(key)
        )
        assert response.status_code == 202, f"key {key!r} should authenticate"


def test_no_configured_keys_rejects_everything() -> None:
    """With an empty API_KEYS the service accepts no collector at all."""
    settings = Settings(_env_file=None, api_keys="")
    app = create_app(settings=settings, storage=InMemoryEventStorage())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/events", json=VALID_EVENT, headers=auth_headers("anything")
        )
        assert response.status_code == 401


def test_authenticator_unit() -> None:
    authenticator = ApiKeyAuthenticator(("alpha", "beta"))
    assert authenticator.authenticate("alpha") is not None
    assert authenticator.authenticate("beta") is not None
    principal = authenticator.authenticate("alpha")
    assert principal is not None and principal.method == "api_key"
    assert authenticator.authenticate("alph") is None
    assert authenticator.authenticate("alphaa") is None
    assert authenticator.authenticate("") is None
    assert authenticator.authenticate(None) is None


def test_key_never_echoed_in_response(client: TestClient) -> None:
    """Auth failures must not reflect the presented credential."""
    secret_attempt = "super-secret-attempt"
    response = client.post(
        "/api/v1/events", json=VALID_EVENT, headers=auth_headers(secret_attempt)
    )
    assert secret_attempt not in response.text
