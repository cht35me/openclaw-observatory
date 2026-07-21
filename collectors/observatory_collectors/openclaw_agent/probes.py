"""Probes for OpenClaw agent self-monitoring (Mission M003 §3).

Data sources:

* **Agent state file** (``AGENT_STATE_FILE``, JSON): the agent runtime
  maintains a small status document — agent status, active mission, mission
  state, last completed task, model identifier, and optionally a list of
  mission updates to forward. The collector only *reads* it; content is
  validated defensively (free text is data, never instructions —
  docs/security.md §9).
* **CLI probes**: Claude Code availability (``claude --version``) and
  OpenClaw runtime version (``openclaw --version``), both best-effort.
* **/proc**: agent process uptime via the process start time in
  ``/proc/<pid>/stat``.

All probes fail soft and return ``None``/defaults on error.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

_CLI_TIMEOUT = 15.0

#: Fields copied (string-coerced, length-bounded) from the agent state file.
_STATE_FIELDS = (
    "agent_status",
    "active_mission",
    "mission_state",
    "last_completed_task",
    "model",
)
_MAX_FIELD_LENGTH = 512


# --------------------------------------------------------------------- #
# Pure parsers
# --------------------------------------------------------------------- #


def parse_state_document(text: str) -> dict[str, Any]:
    """Validate the agent state JSON into a bounded, string-typed dict."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    state: dict[str, Any] = {}
    for field in _STATE_FIELDS:
        value = raw.get(field)
        if isinstance(value, str) and value.strip():
            state[field] = value.strip()[:_MAX_FIELD_LENGTH]
    missions = raw.get("missions")
    if isinstance(missions, list):
        state["missions"] = [item for item in missions if isinstance(item, dict)]
    return state


def parse_starttime_ticks(proc_stat_text: str) -> int | None:
    """Field 22 (starttime) from ``/proc/<pid>/stat``, tolerant of comm spaces."""
    # comm is parenthesized and may contain spaces; split after the last ')'.
    _, _, rest = proc_stat_text.rpartition(")")
    fields = rest.split()
    # rest starts at field 3 ("state"), so starttime (field 22) is index 19.
    if len(fields) < 20:
        return None
    try:
        return int(fields[19])
    except ValueError:
        return None


def process_uptime_seconds(
    starttime_ticks: int | None, system_uptime: float | None, hertz: int
) -> float | None:
    if starttime_ticks is None or system_uptime is None or hertz <= 0:
        return None
    uptime = system_uptime - starttime_ticks / hertz
    return round(uptime, 3) if uptime >= 0 else None


# --------------------------------------------------------------------- #
# I/O wrappers (fail soft)
# --------------------------------------------------------------------- #


def read_state_file(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        return parse_state_document(Path(path).read_text(encoding="utf-8"))
    except OSError:
        return {}


def _cli_version(binary: str) -> str | None:
    if shutil.which(binary) is None:
        return None
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=_CLI_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    output = (result.stdout or result.stderr).strip()
    return output.splitlines()[0][:_MAX_FIELD_LENGTH] if output else None


def probe_claude_code() -> dict[str, Any]:
    """Claude Code availability + version (M003 §3)."""
    version = _cli_version("claude")
    return {"available": version is not None, "version": version}


def probe_runtime_version() -> str | None:
    """OpenClaw runtime version (falls back to the Node.js version)."""
    version = _cli_version("openclaw")
    if version:
        return version
    node = _cli_version("node")
    return f"node {node}" if node else None


def probe_process_uptime(pattern: str = "openclaw") -> float | None:
    """Uptime of the oldest process matching ``pattern`` (pgrep -f)."""
    try:
        result = subprocess.run(
            ["pgrep", "-o", "-f", pattern],
            capture_output=True,
            text=True,
            timeout=_CLI_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    pid = result.stdout.strip().splitlines()[0] if result.returncode == 0 else ""
    if not pid.isdigit():
        return None
    try:
        stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        uptime_text = Path("/proc/uptime").read_text(encoding="utf-8")
    except OSError:
        return None
    system_uptime = float(uptime_text.split()[0])
    hertz = os.sysconf("SC_CLK_TCK")
    return process_uptime_seconds(parse_starttime_ticks(stat_text), system_uptime, hertz)
