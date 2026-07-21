"""Observatory Monitor tests (SD-020): rendering logic and the /monitor route."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.models.mission import MissionRecord
from app.services.monitor import (
    MonitorSnapshot,
    _fmt_bytes,
    _fmt_duration,
    _fmt_percent,
    render_monitor_html,
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
    # Token usage is a recorded open question — shown as a placeholder.
    assert "Token usage" in html and "not yet collected" in html


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
