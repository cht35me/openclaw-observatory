"""Docker telemetry via the docker CLI (Mission M003 §10).

Everything on the fleet is containerized, so container health is first-class
telemetry: daemon status, running/failed containers, restart counts, and
per-container CPU/RAM.

Uses the ``docker`` CLI (the collector user is in the ``docker`` group)
instead of a third-party SDK — consistent with the stdlib-only collector rule
(SD-019, proposed). Pure parse functions take command output; ``collect()``
does the subprocess I/O and fails soft (a stopped daemon is *telemetry*, not
an error).
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

_CLI_TIMEOUT = 20.0


# --------------------------------------------------------------------- #
# Pure parsers (tested with canned CLI output)
# --------------------------------------------------------------------- #


def parse_inspect_output(inspect_json: str) -> list[dict[str, Any]]:
    """Container facts from ``docker inspect`` JSON (name, state, restarts)."""
    try:
        raw = json.loads(inspect_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    containers: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        state = entry.get("State") or {}
        containers.append(
            {
                "name": str(entry.get("Name", "")).lstrip("/"),
                "image": (entry.get("Config") or {}).get("Image"),
                "status": state.get("Status"),
                "exit_code": state.get("ExitCode"),
                "restart_count": entry.get("RestartCount", 0),
                "started_at": state.get("StartedAt"),
            }
        )
    return containers


def parse_stats_output(stats_lines: str) -> dict[str, dict[str, Any]]:
    """Per-container CPU/RAM from ``docker stats --no-stream --format json``."""
    stats: dict[str, dict[str, Any]] = {}
    for line in stats_lines.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = entry.get("Name")
        if not name:
            continue
        stats[name] = {
            "cpu_percent": _percent(entry.get("CPUPerc")),
            "memory_percent": _percent(entry.get("MemPerc")),
            "memory_usage": entry.get("MemUsage"),
        }
    return stats


def _percent(raw: Any) -> float | None:
    if not isinstance(raw, str):
        return None
    try:
        return float(raw.strip().rstrip("%"))
    except ValueError:
        return None


def summarize(containers: list[dict[str, Any]]) -> dict[str, int]:
    """Aggregate counts the dashboard cares about."""
    running = sum(1 for c in containers if c.get("status") == "running")
    failed = sum(
        1
        for c in containers
        if c.get("status") in ("exited", "dead") and (c.get("exit_code") or 0) != 0
    )
    restarts = sum(int(c.get("restart_count") or 0) for c in containers)
    return {
        "containers_total": len(containers),
        "containers_running": running,
        "containers_failed": failed,
        "restart_count_total": restarts,
    }


# --------------------------------------------------------------------- #
# CLI wrappers (fail soft)
# --------------------------------------------------------------------- #


def _run(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=_CLI_TIMEOUT, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def collect() -> dict[str, Any]:
    """Gather one Docker telemetry snapshot (daemon down ⇒ still a payload)."""
    ids_output = _run(["docker", "ps", "-aq"])
    if ids_output is None:
        return {"daemon_running": False}

    container_ids = ids_output.split()
    containers: list[dict[str, Any]] = []
    if container_ids:
        inspect_output = _run(["docker", "inspect", *container_ids])
        containers = parse_inspect_output(inspect_output or "[]")

        stats_output = _run(["docker", "stats", "--no-stream", "--format", "{{json .}}"])
        stats = parse_stats_output(stats_output or "")
        for container in containers:
            container.update(stats.get(container["name"], {}))

    return {
        "daemon_running": True,
        **summarize(containers),
        "containers": containers,
    }
