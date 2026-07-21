"""Docker telemetry parser tests (M003 §10) with canned CLI output."""

from __future__ import annotations

import json

from observatory_collectors.host_pi import docker_stats

INSPECT = json.dumps(
    [
        {
            "Name": "/observatory-backend",
            "RestartCount": 2,
            "Config": {"Image": "openclaw-observatory-backend"},
            "State": {"Status": "running", "ExitCode": 0, "StartedAt": "2026-07-20T00:00:00Z"},
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


def test_malformed_output_fails_soft() -> None:
    assert docker_stats.parse_inspect_output("not json") == []
    assert docker_stats.parse_inspect_output('{"a": 1}') == []
    assert docker_stats.parse_stats_output("garbage\n{}") == {}
