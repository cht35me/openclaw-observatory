"""Observatory Monitor tests (SD-020): rendering logic and the /monitor route."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.models.event import Event
from app.models.mission import MissionRecord
from app.models.registry import (
    AssetType,
    Connectivity,
    Environment,
    FleetAssetView,
    HealthStatus,
    HeartbeatInfo,
    LifecycleStatus,
)
from app.services.monitor import (
    MonitorSnapshot,
    _fmt_bytes,
    _fmt_duration,
    _fmt_installed_memory,
    _fmt_last_reboot,
    _fmt_percent,
    _fmt_used,
    render_monitor_html,
    resolve_display_timezone,
)
from tests.conftest import auth_headers

NOW = datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)


def _snapshot(**overrides) -> MonitorSnapshot:
    defaults = dict(
        generated_at=NOW,
        backend_version="0.0.0-test",
        backend_fleet_id="OBLN01",
        backend_uptime_seconds=3700.0,
        database_connected=True,
    )
    defaults.update(overrides)
    return MonitorSnapshot(**defaults)


# --------------------------------------------------------------------- #
# Pure rendering
# --------------------------------------------------------------------- #


def test_formatters() -> None:
    assert _fmt_percent(27.71) == "27.7%"
    assert _fmt_percent(None) == "—"
    assert _fmt_percent(True) == "—"  # booleans are not numbers here
    assert _fmt_bytes(1102958592) == "1.0 GiB"
    assert _fmt_bytes(512) == "512.0 B"
    assert _fmt_bytes("x") == "—"
    assert _fmt_duration(59) == "59s"
    assert _fmt_duration(3700) == "1h 1m"
    assert _fmt_duration(90_061) == "1d 1h 1m"
    assert _fmt_duration(None) == "—"


def test_render_empty_snapshot_degrades_gracefully() -> None:
    html = render_monitor_html(_snapshot(database_connected=False))
    assert "Observatory Monitor" in html
    assert "no missions tracked yet" in html
    assert "no docker telemetry received yet" in html
    assert "registry is empty" in html
    assert "unreachable" in html  # database badge
    assert 'http-equiv="refresh"' in html
    # Deployment header degrades honestly with no commit / no mission.
    assert "commit unknown" in html
    assert "mission none" in html


def _mission(mission_id: str, state: str) -> MissionRecord:
    return MissionRecord(
        mission_id=mission_id,
        title=f"Mission {mission_id}",
        assigned_agent="A001",
        state=state,
        created_at=NOW,
        pr_ref=None,
        commit_sha=None,
        updated_at=NOW,
    )


def test_header_shows_deployment_information() -> None:
    """Version, git commit, and active mission identify the deployment."""
    html = render_monitor_html(
        _snapshot(
            git_commit="e3bf1a3deadbeefcafe0123456789abcdef01234",
            agent_status={"active_mission": "M003", "mission_state": "Running"},
        )
    )
    assert "v0.0.0-test" in html
    assert "commit e3bf1a3deadb" in html  # shortened to 12 chars
    assert "e3bf1a3deadbeefcafe" not in html  # full SHA not dumped
    assert "mission M003 (Running)" in html


def test_header_active_mission_falls_back_to_projection() -> None:
    """Without an agent report, the newest non-Completed mission is shown."""
    html = render_monitor_html(
        _snapshot(missions=[_mission("M002", "Completed"), _mission("M003", "Review")])
    )
    assert "mission M003 (Review)" in html

    html = render_monitor_html(_snapshot(missions=[_mission("M002", "Completed")]))
    assert "mission none" in html  # only completed missions → nothing active


def test_render_includes_live_values() -> None:
    html = render_monitor_html(
        _snapshot(
            host_fleet_id="RPSG01",
            host_metrics={
                "cpu": {
                    "utilization_percent": 12.5,
                    "temperature_c": 55.2,
                    "load_avg_1m": 0.4,
                    "load_avg_5m": 0.3,
                    "load_avg_15m": 0.2,
                },
                "memory": {
                    "total_bytes": 3980185600,
                    "used_bytes": 1102958592,
                    "used_percent": 27.7,
                },
                "disk": {
                    "total_bytes": 60605497344,
                    "free_bytes": 42194640896,
                    "used_percent": 26.2,
                },
                "uptime_seconds": 46932.0,
                "network": {
                    "online": True,
                    "ip_address": "192.168.1.2",
                    "default_interface": "eth0",
                },
            },
            host_metrics_at=NOW - timedelta(seconds=30),
            docker={
                "daemon_running": True,
                "summary": {
                    "containers_total": 1,
                    "containers_running": 1,
                    "containers_failed": 0,
                    "restart_count_total": 0,
                },
                "containers": [
                    {
                        "name": "bitaxe-exporter",
                        "image": "bitaxe-monitoring-bitaxe-exporter",
                        "status": "running",
                        "restart_count": 0,
                        "cpu_percent": 0.5,
                        "memory_percent": 1.2,
                    }
                ],
            },
            agent_fleet_id="A001",
            agent_status={
                "agent_status": "active",
                "active_mission": "M003",
                "mission_state": "EXECUTING",
                "model": "anthropic/claude-fable-5",
                "runtime_version": "Python 3.13.5",
                "claude_code": {"available": True, "version": "2.0"},
                "process_uptime_seconds": 4000,
            },
            agent_status_at=NOW - timedelta(seconds=10),
        )
    )
    assert "12.5%" in html  # CPU utilization
    assert "55.2 °C" in html  # CPU temperature
    assert "27.7% used" in html  # RAM
    assert "192.168.1.2" in html
    assert "bitaxe-exporter" in html
    assert "M003" in html
    assert "anthropic/claude-fable-5" in html
    assert "30s ago" in html
    # Token usage: ruled architecture pointer (M003.5 §5), not a bare
    # placeholder.
    assert "Token usage" in html
    assert "runtime-owned, agent collector transport" in html
    assert "token-usage-architecture" in html


INVENTORY = {
    "hardware": {
        "manufacturer": "Raspberry Pi Foundation",
        "model": "Raspberry Pi 4 Model B",
        "revision": "c03114",
        "cpu_model": "BCM2711",
        "cpu_architecture": "ARM64",
        "cpu_cores": 4,
        "memory_total_bytes": 3980185600,
        "serial": "10000000bbc78bf0",
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
            "total_bytes": 60605497344,
            "used_bytes": 18484989952,
            "free_bytes": 42120507392,
            "used_percent": 30.5,
        }
    ],
    "network": {
        "interfaces": [
            {"name": "eth0", "ipv4": "192.168.1.2", "link_state": "up"},
            {"name": "tailscale0", "ipv4": "100.80.1.2", "link_state": "unknown"},
            {"name": "wlan0", "ipv4": None, "link_state": "down"},
        ],
        "default_route": {"gateway": "192.168.1.254", "interface": "eth0"},
    },
    "maintenance": {
        "last_apt_update_epoch": int((NOW - timedelta(hours=3)).timestamp()),
        "last_apt_upgrade": "2026-07-21 06:24:42",
        "last_apt_full_upgrade": "2026-07-14 15:55:26",
        "updates_available": 25,
        "reboot_required": False,
    },
}


def test_fmt_last_reboot_humanization() -> None:
    noon = datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)
    assert _fmt_last_reboot(3600, noon) == "Today 11:00 (+00)"
    assert _fmt_last_reboot(13 * 3600, noon) == "Yesterday 23:00 (+00)"
    assert _fmt_last_reboot(3 * 86400 + 60, noon) == "3 days ago"
    assert _fmt_last_reboot(None, noon) == "—"
    assert _fmt_last_reboot("x", noon) == "—"


def test_fmt_last_reboot_in_display_timezone() -> None:
    """Day boundaries follow DISPLAY_TZ, not UTC (M003.6 §3)."""
    sg = ZoneInfo("Asia/Singapore")
    # Boot 2026-07-21 16:30Z = 2026-07-22 00:30 +08 — "Today" in Singapore
    # even though it is still "yesterday" in UTC terms.
    now = datetime(2026, 7, 21, 17, 0, 0, tzinfo=UTC)  # 2026-07-22 01:00 +08
    assert _fmt_last_reboot(1800, now, sg) == "Today 00:30 (+08)"
    # The same instant renders as Today 16:30 in UTC.
    assert _fmt_last_reboot(1800, now, UTC) == "Today 16:30 (+00)"
    # Boot 2026-07-21 15:30Z = 23:30 +08 — "Yesterday" in Singapore,
    # still "Today" in UTC.
    assert _fmt_last_reboot(5400, now, sg) == "Yesterday 23:30 (+08)"
    assert _fmt_last_reboot(5400, now, UTC) == "Today 15:30 (+00)"
    # Non-whole-hour offsets carry minutes in the suffix.
    india = ZoneInfo("Asia/Kolkata")
    assert _fmt_last_reboot(1800, now, india) == "Today 22:00 (+05:30)"
    # Negative offsets keep the sign.
    lima = ZoneInfo("America/Lima")
    assert _fmt_last_reboot(1800, now, lima) == "Today 11:30 (-05)"


def test_resolve_display_timezone() -> None:
    """Explicit override, default (host local), and safe fallback (M003.6 §3)."""
    # Explicit IANA override wins.
    assert str(resolve_display_timezone("Asia/Singapore")) == "Asia/Singapore"
    # Empty / None -> host local timezone; must be usable, never raise.
    for value in ("", None, "   "):
        tz = resolve_display_timezone(value)
        assert NOW.astimezone(tz).utcoffset() is not None
    # Invalid names fall back safely to the host timezone (never break the
    # page); the fallback equals the default resolution.
    fallback = resolve_display_timezone("Not/A_Zone")
    assert NOW.astimezone(fallback) == NOW.astimezone(resolve_display_timezone(""))


def test_snapshot_display_tz_reaches_last_reboot_row() -> None:
    """The rendered System section uses the snapshot's display timezone."""
    now = datetime(2026, 7, 21, 17, 0, 0, tzinfo=UTC)
    snapshot = _snapshot(
        generated_at=now,
        host_fleet_id="RPSG01",
        host_metrics={"uptime_seconds": 1800},
        host_metrics_at=now,
        display_tz=ZoneInfo("Asia/Singapore"),
    )
    html = render_monitor_html(snapshot)
    assert "Today 00:30 (+08)" in html
    # The footer stays UTC (internal timestamps unchanged).
    assert "generated 2026-07-21 17:00:00 UTC" in html


def test_fmt_used_and_installed_memory() -> None:
    assert _fmt_used(6_657_199_308, 28.0) == "6.2 GiB (28.0%)"
    assert _fmt_used(None, None) == "—"
    assert _fmt_installed_memory(3980185600) == "4 GB"  # §3a example
    assert _fmt_installed_memory(536870912) == "512.0 MiB"
    assert _fmt_installed_memory(None) == "—"


def test_system_summary_renders_inventory() -> None:
    html = render_monitor_html(
        _snapshot(
            host_fleet_id="RPSG01",
            host_inventory=INVENTORY,
            host_inventory_at=NOW - timedelta(minutes=5),
            host_metrics={"uptime_seconds": 46932.0},
        )
    )
    assert "Raspberry Pi Foundation" in html
    assert "Raspberry Pi 4 Model B (rev c03114)" in html
    assert "BCM2711 · ARM64 · 4 cores" in html
    assert "4 GB" in html
    assert "Debian GNU/Linux Trixie" in html
    assert "6.18.34+rpt-rpi-v8" in html
    assert "Today" in html or "Yesterday" in html  # last reboot humanized
    # Maintenance status (§3d)
    assert "2026-07-14 15:55:26" in html  # last full-upgrade
    assert "Updates available" in html and "25" in html
    assert "Reboot required" in html


def test_storage_section_renders_inventory_table() -> None:
    html = render_monitor_html(_snapshot(host_inventory=INVENTORY))
    assert "<th>Device</th>" in html and "<th>Transport</th>" in html
    assert "SD1" in html
    assert "SD Card" in html
    assert "SPCC" in html
    assert "ext4" in html
    # Used as actual + percent (§3-monitor): 18484989952 B ≈ 17.2 GiB.
    assert "17.2 GiB (30.5%)" in html


def test_storage_section_falls_back_to_single_disk_line() -> None:
    html = render_monitor_html(
        _snapshot(
            host_metrics={
                "disk": {
                    "path": "/",
                    "total_bytes": 60605497344,
                    "used_bytes": 18484989952,
                    "free_bytes": 42120507392,
                    "used_percent": 30.5,
                }
            }
        )
    )
    assert "Disk /" in html
    assert "17.2 GiB (30.5%)" in html
    assert "<th>Transport</th>" not in html  # no inventory table yet

    empty = render_monitor_html(_snapshot())
    assert "no storage inventory received yet" in empty


def test_interfaces_section_renders_state_and_default_route() -> None:
    html = render_monitor_html(_snapshot(host_inventory=INVENTORY))
    assert "eth0" in html and "192.168.1.2" in html
    assert "tailscale0" in html and "100.80.1.2" in html
    assert ">UP<" in html and ">DOWN<" in html and ">UNKNOWN<" in html
    assert "Default route: 192.168.1.254" in html and "dev eth0" in html

    empty = render_monitor_html(_snapshot())
    assert "no interface inventory received yet" in empty


def test_docker_extended_columns() -> None:
    html = render_monitor_html(
        _snapshot(
            docker={
                "daemon_running": True,
                "summary": {"containers_total": 1, "containers_running": 1},
                "containers": [
                    {
                        "name": "bitaxe-exporter",
                        "image": "bitaxe",
                        "status": "running",
                        "network_mode": "bitaxe-monitoring_default",
                        "uptime_seconds": 90061.0,
                        "cpu_percent": 0.5,
                        "memory_percent": 1.2,
                        "network_rx_bytes": 21_000_000,
                        "network_tx_bytes": 13_000_000,
                        "restart_count": 4,
                    }
                ],
            }
        )
    )
    for column in ("Network", "Uptime", "RX", "TX", "Restarts"):
        assert f"<th>{column}</th>" in html
    assert "bitaxe-monitoring_default" in html
    assert "1d 1h 1m" in html
    assert "20.0 MiB" in html  # RX humanized
    assert "12.4 MiB" in html  # TX humanized
    assert "<td>4</td>" in html  # restart count


def _event(event_type: str, payload: dict, collector_id: str = "OBLN01") -> Event:
    return Event(
        id=uuid4(),
        collector_id=collector_id,
        timestamp=NOW - timedelta(minutes=1),
        event_type=event_type,
        payload=payload,
        schema_version=1,
        received_at=NOW - timedelta(minutes=1),
    )


def test_recent_events_section_details() -> None:
    html = render_monitor_html(
        _snapshot(
            recent_events=[
                _event(
                    "mission_update",
                    {"mission_id": "M003.5", "state": "Running", "backfill": True},
                    collector_id="A001",
                ),
                _event(
                    "asset_offline",
                    {"previous": "online", "current": "offline"},
                    collector_id="RPSG01",
                ),
                _event(
                    "service_start",
                    {"version": "0.1.0", "git_commit": "e3bf1a3deadbeefcafe"},
                ),
            ]
        )
    )
    assert "Recent Events (last 20)" in html
    assert "M003.5 → Running (backfill)" in html
    assert "online → offline" in html
    assert "v0.1.0 · commit e3bf1a3deadb" in html
    # Heartbeat-exclusion rationale is stated on the page.
    assert "heartbeats are summarized" in html

    empty = render_monitor_html(_snapshot())
    assert "no notable events yet" in empty


def test_recent_events_are_escaped() -> None:
    html = render_monitor_html(
        _snapshot(
            recent_events=[
                _event("mission_update", {"mission_id": "<img src=x>", "state": "Running"})
            ]
        )
    )
    assert "<img" not in html
    assert "&lt;img" in html


def test_inventory_strings_are_escaped() -> None:
    """Inventory text is telemetry: rendered inert (security.md §9)."""
    hostile = {
        "hardware": {"manufacturer": "<script>alert(1)</script>"},
        "os": {"name": "<b>Debian</b>"},
        "storage": [{"name": "SD1", "brand": "<i>Evil</i>", "mount": "/"}],
        "network": {"interfaces": [{"name": "<script>eth0</script>", "link_state": "up"}]},
    }
    html = render_monitor_html(_snapshot(host_inventory=hostile))
    assert "<script>" not in html
    assert "<b>Debian</b>" not in html
    assert "<i>Evil</i>" not in html
    assert "&lt;script&gt;" in html


def _asset_view(fleet_id: str, collector_version: str | None) -> FleetAssetView:
    heartbeat = None
    if collector_version is not None:
        heartbeat = HeartbeatInfo(
            timestamp=NOW - timedelta(seconds=30),
            received_at=NOW - timedelta(seconds=30),
            collector_version=collector_version,
        )
    return FleetAssetView(
        fleet_id=fleet_id,
        asset_type=AssetType.NODE,
        nickname=None,
        hostname="host",
        role="role",
        location="loc",
        platform="platform",
        os="Linux",
        software_version=None,
        host_fleet_id=None,
        deployment_role=None,
        service_version=None,
        capabilities=(),
        tags=(),
        status=LifecycleStatus.ACTIVE,
        environment=Environment.PRODUCTION,
        registered_at=NOW,
        updated_at=NOW,
        last_heartbeat=heartbeat,
        connectivity=Connectivity.ONLINE,
        health=HealthStatus.HEALTHY,
    )


def test_header_shows_build_metadata_and_collector_versions() -> None:
    html = render_monitor_html(
        _snapshot(
            build_timestamp="2026-07-21T10:00:00+08:00",
            deployment_environment="Production",
            assets=[
                _asset_view("RPSG01", "1.0.0"),
                _asset_view("A001", "1.0.0"),
                _asset_view("SILENT01", None),
            ],
        )
    )
    assert "built 2026-07-21T10:00:00+08:00" in html
    assert "env Production" in html
    assert "RPSG01 v1.0.0" in html and "A001 v1.0.0" in html
    assert "SILENT01 v" not in html  # no heartbeat → not listed

    bare = render_monitor_html(_snapshot(build_timestamp=None))
    assert "built unknown" in bare
    assert "collectors none reporting" in bare


def test_render_escapes_telemetry_text() -> None:
    """Telemetry strings are rendered inert (security.md §9)."""
    html = render_monitor_html(
        _snapshot(
            agent_fleet_id="A001",
            agent_status={"agent_status": "<script>alert(1)</script>"},
        )
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# --------------------------------------------------------------------- #
# Route (wired app, in-memory storage, seeded registry)
# --------------------------------------------------------------------- #


def test_monitor_route_serves_html_without_auth(client: TestClient) -> None:
    """/monitor mirrors /health exposure (SD-020): network-boundary protected."""
    response = client.get("/monitor")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    # Seeded registry assets are visible.
    for fleet_id in ("A001", "RPSG01", "OBLN01"):
        assert fleet_id in response.text
    # Deployment header is present (tests run inside the git checkout,
    # so a real commit is detected rather than "unknown").
    assert "commit " in response.text
    assert "commit unknown" not in response.text
    # The backend records its own start (M003.5 §4) — visible immediately.
    assert "service_start" in response.text
    # Build & release metadata (M003.5 §6) is in the header.
    assert "built " in response.text
    assert "env Development" in response.text  # test settings default


def test_monitor_route_reflects_ingested_telemetry(client: TestClient) -> None:
    now = datetime.now(UTC).isoformat()
    submit = client.post(
        "/api/v1/events",
        headers=auth_headers("test-key-rpsg01"),
        json={
            "collector_id": "RPSG01",
            "timestamp": now,
            "event_type": "system_metrics",
            "schema_version": 1,
            "payload": {
                "cpu": {"utilization_percent": 42.0, "temperature_c": 61.3},
                "memory": {"used_percent": 33.3},
                "disk": {"used_percent": 26.2},
                "uptime_seconds": 1000,
                "network": {"online": True, "ip_address": "10.0.0.7"},
            },
        },
    )
    assert submit.status_code == 202

    html = client.get("/monitor").text
    assert "42.0%" in html
    assert "61.3 °C" in html
    assert "10.0.0.7" in html


def test_monitor_is_read_only(client: TestClient) -> None:
    assert client.post("/monitor").status_code == 405


def test_version_label_no_double_v_prefix() -> None:
    """APP_VERSION equals the release tag (v0.2.0); header must not show vv0.2.0."""
    from app.services.monitor import _version_label

    assert _version_label("v0.2.0") == "v0.2.0"
    assert _version_label("0.1.0") == "v0.1.0"
