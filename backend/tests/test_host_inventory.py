"""Host Inventory ingestion, projection, and API tests (Mission M003.5 §3)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.models.inventory import HostInventoryRecord
from app.storage.memory import InMemoryHostInventoryStorage
from tests.conftest import auth_headers

INVENTORY_PAYLOAD = {
    "hardware": {
        "manufacturer": "Raspberry Pi Foundation",
        "model": "Raspberry Pi 4 Model B",
        "revision": "c03114",
        "cpu_architecture": "ARM64",
        "memory_total_bytes": 3980185600,
    },
    "os": {
        "name": "Debian GNU/Linux",
        "release": "Trixie",
        "kernel": "6.18.34+rpt-rpi-v8",
        "hostname": "raspberrypi-sg01",
    },
    "storage": [
        {
            "name": "SD1",
            "device": "/dev/mmcblk0p2",
            "type": "SD Card",
            "transport": "SD",
            "capacity_bytes": 62192091136,
            "mount": "/",
            "brand": "SPCC",
            "filesystem": "ext4",
            "used_bytes": 18484989952,
            "used_percent": 30.5,
            # SMART-extensibility: unknown keys must be preserved verbatim.
            "smart_health": "PASSED",
        }
    ],
    "network": {
        "interfaces": [{"name": "eth0", "ipv4": "192.168.1.2", "link_state": "up"}],
        "default_route": {"gateway": "192.168.1.254", "interface": "eth0"},
    },
    "maintenance": {"reboot_required": False, "updates_available": 25},
}


def _submit_inventory(client: TestClient, payload: dict | None = None) -> object:
    return client.post(
        "/api/v1/events",
        headers=auth_headers("test-key-rpsg01"),
        json={
            "collector_id": "RPSG01",
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": "host_inventory",
            "schema_version": 1,
            "payload": INVENTORY_PAYLOAD if payload is None else payload,
        },
    )


def test_host_inventory_ingested_and_projected(
    client: TestClient, inventory_storage: InMemoryHostInventoryStorage
) -> None:
    response = _submit_inventory(client)
    assert response.status_code == 202

    record = client.portal.call(lambda: inventory_storage.get_inventory("RPSG01"))
    assert record is not None
    assert record.fleet_id == "RPSG01"
    assert record.payload == INVENTORY_PAYLOAD  # extra keys preserved verbatim
    assert record.reported_at.tzinfo is not None


def test_host_inventory_latest_row_wins(
    client: TestClient, inventory_storage: InMemoryHostInventoryStorage
) -> None:
    assert _submit_inventory(client).status_code == 202
    updated = {**INVENTORY_PAYLOAD, "os": {**INVENTORY_PAYLOAD["os"], "kernel": "6.19.0"}}
    assert _submit_inventory(client, payload=updated).status_code == 202

    record = client.portal.call(lambda: inventory_storage.get_inventory("RPSG01"))
    assert record.payload["os"]["kernel"] == "6.19.0"
    listing = client.portal.call(inventory_storage.list_inventories)
    assert [r.fleet_id for r in listing] == ["RPSG01"]


def test_host_inventory_rejects_unknown_identity(client: TestClient) -> None:
    """Collectors can never introduce identities via telemetry (M003 §1)."""
    response = client.post(
        "/api/v1/events",
        headers=auth_headers("test-key-alpha"),  # bound to "demo", not registered
        json={
            "collector_id": "demo",
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": "host_inventory",
            "payload": INVENTORY_PAYLOAD,
        },
    )
    assert response.status_code == 403


def test_host_inventory_rejects_empty_payload(client: TestClient) -> None:
    assert _submit_inventory(client, payload={}).status_code == 422


def test_inventory_api_returns_latest_record(client: TestClient) -> None:
    assert _submit_inventory(client).status_code == 202
    response = client.get("/api/v1/fleet/RPSG01/inventory", headers=auth_headers("test-key-a001"))
    assert response.status_code == 200
    body = response.json()
    assert body["fleet_id"] == "RPSG01"
    assert body["payload"]["hardware"]["model"] == "Raspberry Pi 4 Model B"
    assert body["payload"]["storage"][0]["smart_health"] == "PASSED"


def test_inventory_api_requires_auth_and_404s(client: TestClient) -> None:
    assert client.get("/api/v1/fleet/RPSG01/inventory").status_code == 401
    # Known asset, no inventory reported yet.
    response = client.get("/api/v1/fleet/RPSG01/inventory", headers=auth_headers("test-key-a001"))
    assert response.status_code == 404
    # Unknown asset.
    response = client.get("/api/v1/fleet/NOPE01/inventory", headers=auth_headers("test-key-a001"))
    assert response.status_code == 404


def test_monitor_renders_ingested_inventory(client: TestClient) -> None:
    """End to end: host_inventory event → System/Storage/Interfaces sections."""
    assert _submit_inventory(client).status_code == 202
    html = client.get("/monitor").text
    assert "Raspberry Pi 4 Model B (rev c03114)" in html
    assert "Debian GNU/Linux Trixie" in html
    assert "SD Card" in html and "SPCC" in html
    assert "17.2 GiB (30.5%)" in html
    assert "Default route: 192.168.1.254" in html


def test_memory_inventory_storage_failure_mode() -> None:
    import asyncio

    from app.storage.base import StorageError

    async def scenario() -> None:
        storage = InMemoryHostInventoryStorage()
        now = datetime.now(UTC)
        record = HostInventoryRecord(
            fleet_id="RPSG01", payload={"os": {}}, reported_at=now, updated_at=now
        )
        await storage.upsert_inventory(record)
        assert (await storage.get_inventory("RPSG01")) == record
        assert await storage.list_inventories() == [record]
        assert await storage.get_inventory("OTHER") is None

        storage.fail = True
        try:
            await storage.get_inventory("RPSG01")
        except StorageError:
            pass
        else:  # pragma: no cover
            raise AssertionError("expected StorageError")

    asyncio.run(scenario())
