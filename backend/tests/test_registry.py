"""Fleet Registry tests (M003 §1/§7): seeding, source of truth, read API."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.services.seed import SEED_ASSETS, seed_registry
from app.storage.memory import InMemoryRegistryStorage
from tests.conftest import auth_headers

SEED_IDS = {entry["fleet_id"] for entry in SEED_ASSETS}


def test_seed_contains_required_assets() -> None:
    """FLEET.md-derived seed must include A001, RPSG01 and the backend."""
    assert {"A001", "RPSG01", "OBS01"} <= SEED_IDS


def test_seeding_is_create_only() -> None:
    """Re-seeding never overwrites existing entries (lifecycle survives restarts)."""

    async def scenario() -> None:
        registry = InMemoryRegistryStorage()
        created_first = await seed_registry(registry)
        assert created_first == len(SEED_ASSETS)

        # Mutate one entry as an operator would (lifecycle change).
        asset = await registry.get_asset("A001")
        modified = asset.model_copy(update={"nickname": "Ada"})
        await registry.upsert_asset(modified)

        created_second = await seed_registry(registry)
        assert created_second == 0
        assert (await registry.get_asset("A001")).nickname == "Ada"

    asyncio.run(scenario())


def test_fleet_list_requires_auth(client: TestClient) -> None:
    """No anonymous reads, ever (security.md §3)."""
    assert client.get("/api/v1/fleet").status_code == 401
    assert client.get("/api/v1/fleet/A001").status_code == 401
    assert client.get("/api/v1/missions").status_code == 401
    assert client.get("/api/v1/missions/M003").status_code == 401


def test_fleet_list_returns_seeded_assets(client: TestClient) -> None:
    response = client.get("/api/v1/fleet", headers=auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert {asset["fleet_id"] for asset in body} == SEED_IDS

    by_id = {asset["fleet_id"]: asset for asset in body}
    a001 = by_id["A001"]
    assert a001["role"] == "Autonomous Software Engineering Agent"
    assert "missions" in a001["capabilities"]
    assert "singapore" in a001["tags"]
    assert a001["status"] == "Active"
    # No heartbeat has ever been received in a fresh test app.
    assert a001["connectivity"] == "unknown"
    assert a001["health"] == "Unknown"
    assert a001["last_heartbeat"] is None
    assert a001["registered_at"] is not None


def test_fleet_detail_and_404(client: TestClient) -> None:
    ok = client.get("/api/v1/fleet/RPSG01", headers=auth_headers())
    assert ok.status_code == 200
    assert ok.json()["platform"] == "Raspberry Pi"

    missing = client.get("/api/v1/fleet/NOPE01", headers=auth_headers())
    assert missing.status_code == 404


def test_heartbeat_updates_derived_view(client: TestClient) -> None:
    """A fresh heartbeat flips connectivity to online and surfaces versions."""
    now = datetime.now(UTC).isoformat()
    response = client.post(
        "/api/v1/events",
        json={
            "collector_id": "RPSG01",
            "timestamp": now,
            "event_type": "heartbeat",
            "schema_version": 3,
            "payload": {
                "collector_type": "raspberry",
                "collector_version": "1.2.0",
                "software_version": "bookworm-2026.07",
                "uptime_seconds": 12.5,
                "failures_total": 0,
            },
        },
        headers=auth_headers("test-key-rpsg01"),
    )
    assert response.status_code == 202

    view = client.get("/api/v1/fleet/RPSG01", headers=auth_headers()).json()
    assert view["connectivity"] == "online"
    assert view["health"] == "Healthy"
    assert view["software_version"] == "bookworm-2026.07"
    hb = view["last_heartbeat"]
    assert hb["collector_type"] == "raspberry"
    assert hb["collector_version"] == "1.2.0"
    assert hb["schema_version"] == 3


def test_registry_has_no_write_routes(client: TestClient) -> None:
    """Collectors must never create or modify identities through the API."""
    for method in ("post", "put", "patch"):
        response = getattr(client, method)(
            "/api/v1/fleet", headers=auth_headers(), json={}
        )
        assert response.status_code == 405, method
    assert client.delete("/api/v1/fleet", headers=auth_headers()).status_code == 405
    assert (
        client.put("/api/v1/fleet/A001", headers=auth_headers(), json={}).status_code
        == 405
    )
