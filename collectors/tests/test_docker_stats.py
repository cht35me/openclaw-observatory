"""Docker telemetry parser tests (M003 §10, M003.5 extended stats)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from observatory_collectors.host_pi import docker_stats

INSPECT = json.dumps(
    [
        {
            "Name": "/observatory-backend",
            "RestartCount": 2,
            "Config": {"Image": "openclaw-observatory-backend"},
            "State": {"Status": "running", "ExitCode": 0, "StartedAt": "2026-07-20T00:00:00Z"},
            "HostConfig": {"NetworkMode": "observatory_default"},
            "NetworkSettings": {"Networks": {"observatory_default": {}}},
        },
        {
            "Name": "/clickhouse",
            "RestartCount": 0,
            "Config": {"Image": "clickhouse/clickhouse-server:26.3.10"},
            "State": {"Status": "exited", "ExitCode": 137, "StartedAt": "2026-07-19T00:00:00Z"},
        },
        {
            "Name": "/idle-helper",
            "RestartCount": 1,
            "Config": {"Image": "helper"},
            "State": {"Status": "exited", "ExitCode": 0, "StartedAt": "2026-07-18T00:00:00Z"},
        },
    ]
)

STATS = "\n".join(
    [
        json.dumps(
            {
                "Name": "observatory-backend",
                "CPUPerc": "1.25%",
                "MemPerc": "3.50%",
                "MemUsage": "132MiB / 3.7GiB",
                "NetIO": "21MB / 1.44kB",
            }
        ),
    ]
)


def test_inspect_parsing_and_summary() -> None:
    containers = docker_stats.parse_inspect_output(INSPECT)
    assert [c["name"] for c in containers] == [
        "observatory-backend",
        "clickhouse",
        "idle-helper",
    ]
    summary = docker_stats.summarize(containers)
    assert summary == {
        "containers_total": 3,
        "containers_running": 1,
        "containers_failed": 1,  # exited non-zero only
        "restart_count_total": 3,
    }


def test_stats_parsing_merges_percentages() -> None:
    stats = docker_stats.parse_stats_output(STATS)
    assert stats["observatory-backend"]["cpu_percent"] == 1.25
    assert stats["observatory-backend"]["memory_percent"] == 3.5
    assert stats["observatory-backend"]["memory_usage"] == "132MiB / 3.7GiB"
    assert stats["observatory-backend"]["network_rx_bytes"] == 21_000_000
    assert stats["observatory-backend"]["network_tx_bytes"] == 1_440


def test_inspect_extracts_network_mode_and_networks() -> None:
    containers = docker_stats.parse_inspect_output(INSPECT)
    backend = containers[0]
    assert backend["network_mode"] == "observatory_default"
    assert backend["networks"] == ["observatory_default"]
    # Containers without network settings fail soft to empty values.
    assert containers[1]["network_mode"] is None
    assert containers[1]["networks"] == []


def test_parse_size_handles_si_and_iec_units() -> None:
    assert docker_stats.parse_size("21MB") == 21_000_000
    assert docker_stats.parse_size("1.44kB") == 1_440
    assert docker_stats.parse_size("2GiB") == 2 * 2**30
    assert docker_stats.parse_size("0B") == 0
    assert docker_stats.parse_size("nonsense") is None
    assert docker_stats.parse_size(None) is None


def test_parse_netio() -> None:
    assert docker_stats.parse_netio("21MB / 13MB") == (21_000_000, 13_000_000)
    assert docker_stats.parse_netio("garbage") == (None, None)
    assert docker_stats.parse_netio(None) == (None, None)


def test_parse_started_at_nanoseconds_and_zero_value() -> None:
    parsed = docker_stats.parse_started_at("2026-07-20T04:03:31.759303729Z")
    assert parsed == datetime(2026, 7, 20, 4, 3, 31, 759303, tzinfo=UTC)
    assert docker_stats.parse_started_at("0001-01-01T00:00:00Z") is None
    assert docker_stats.parse_started_at("not a date") is None
    assert docker_stats.parse_started_at(None) is None


def test_container_uptime_seconds() -> None:
    now = datetime(2026, 7, 21, 4, 3, 31, tzinfo=UTC)
    uptime = docker_stats.container_uptime_seconds("2026-07-20T04:03:31Z", now=now)
    assert uptime == 86400.0
    assert docker_stats.container_uptime_seconds(None, now=now) is None


def test_malformed_output_fails_soft() -> None:
    assert docker_stats.parse_inspect_output("not json") == []
    assert docker_stats.parse_inspect_output('{"a": 1}') == []
    assert docker_stats.parse_stats_output("garbage\n{}") == {}
