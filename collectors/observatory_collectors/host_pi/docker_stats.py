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
import re
import subprocess
from datetime import UTC, datetime
from typing import Any

_CLI_TIMEOUT = 20.0

#: ``docker stats`` sizes: SI (kB/MB/GB, decimal) and IEC (KiB/MiB/GiB).
_SIZE_UNITS = {
    "b": 1,
    "kb": 10**3,
    "mb": 10**6,
    "gb": 10**9,
    "tb": 10**12,
    "kib": 2**10,
    "mib": 2**20,
    "gib": 2**30,
    "tib": 2**40,
}

_SIZE_RE = re.compile(r"^([0-9]*\.?[0-9]+)\s*([A-Za-z]+)$")


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
        networks = (entry.get("NetworkSettings") or {}).get("Networks") or {}
        containers.append(
            {
                "name": str(entry.get("Name", "")).lstrip("/"),
                "image": (entry.get("Config") or {}).get("Image"),
                "status": state.get("Status"),
                "exit_code": state.get("ExitCode"),
                "restart_count": entry.get("RestartCount", 0),
                "started_at": state.get("StartedAt"),
                # M003.5 monitor columns: network mode/name(s).
                "network_mode": (entry.get("HostConfig") or {}).get("NetworkMode"),
                "networks": sorted(str(name) for name in networks),
            }
        )
    return containers


def parse_started_at(started_at: Any) -> datetime | None:
    """Parse Docker's RFC3339 ``StartedAt`` (nanosecond precision, ``Z``)."""
    if not isinstance(started_at, str) or started_at.startswith("0001-"):
        return None  # zero value = never started
    text = started_at.strip().replace("Z", "+00:00")
    # datetime.fromisoformat accepts at most microseconds; trim nanoseconds.
    text = re.sub(r"(\.\d{6})\d+", r"\1", text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def container_uptime_seconds(started_at: Any, now: datetime | None = None) -> float | None:
    """Seconds since the container started (running containers only)."""
    started = parse_started_at(started_at)
    if started is None:
        return None
    now = now or datetime.now(UTC)
    return max(round((now - started).total_seconds(), 1), 0.0)


def parse_size(raw: Any) -> int | None:
    """``docker stats`` size string (``21MB``, ``1.44kB``, ``2GiB``) → bytes."""
    if not isinstance(raw, str):
        return None
    match = _SIZE_RE.match(raw.strip())
    if not match:
        return None
    unit = _SIZE_UNITS.get(match.group(2).lower())
    if unit is None:
        return None
    return int(float(match.group(1)) * unit)


def parse_netio(raw: Any) -> tuple[int | None, int | None]:
    """``NetIO`` column (``"21MB / 13MB"``) → ``(rx_bytes, tx_bytes)``."""
    if not isinstance(raw, str) or "/" not in raw:
        return None, None
    rx_text, _, tx_text = raw.partition("/")
    return parse_size(rx_text.strip()), parse_size(tx_text.strip())


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
        rx_bytes, tx_bytes = parse_netio(entry.get("NetIO"))
        stats[name] = {
            "cpu_percent": _percent(entry.get("CPUPerc")),
            "memory_percent": _percent(entry.get("MemPerc")),
            "memory_usage": entry.get("MemUsage"),
            "network_rx_bytes": rx_bytes,
            "network_tx_bytes": tx_bytes,
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
            if container.get("status") == "running":
                container["uptime_seconds"] = container_uptime_seconds(container.get("started_at"))

    return {
        "daemon_running": True,
        **summarize(containers),
        "containers": containers,
    }
