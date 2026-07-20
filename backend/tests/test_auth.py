"""Tests for collector API-key authentication."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth import ApiKeyAuthenticator
from app.config import Settings
from app.main import create_app
from app.storage.memory import InMemoryEventStorage
from tests.conftest import TEST_KEY_BINDINGS, VALID_EVENT, auth_headers, event_for


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
    """Each key authenticates — for the identity it is bound to (SD-017)."""
    for key, collector_id in TEST_KEY_BINDINGS.items():
        response = client.post(
            "/api/v1/events", json=event_for(collector_id), headers=auth_headers(key)
        )
        assert response.status_code == 202, f"key {key!r} should authenticate"


def test_key_cannot_submit_for_other_collector(client: TestClient) -> None:
    """SD-017: a valid key must not submit events for another collector_id."""
    key, own_identity = next(iter(TEST_KEY_BINDINGS.items()))
    spoofed = event_for("spoofed-collector")
    assert spoofed["collector_id"] != own_identity
    response = client.post("/api/v1/events", json=spoofed, headers=auth_headers(key))
    assert response.status_code == 403


def test_cross_collector_spoofing_rejected(client: TestClient) -> None:
    """SD-017: key A claiming collector B's identity is forbidden."""
    (key_a, collector_a), (_key_b, collector_b) = list(TEST_KEY_BINDINGS.items())[:2]
    assert collector_a != collector_b
    response = client.post(
        "/api/v1/events", json=event_for(collector_b), headers=auth_headers(key_a)
    )
    assert response.status_code == 403


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
    authenticator = ApiKeyAuthenticator((("col-a", "alpha"), ("col-b", "beta")))
    principal_a = authenticator.authenticate("alpha")
    assert principal_a is not None and principal_a.method == "api_key"
    assert principal_a.subject == "col-a"  # SD-017: key resolves to its identity
    principal_b = authenticator.authenticate("beta")
    assert principal_b is not None and principal_b.subject == "col-b"
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
