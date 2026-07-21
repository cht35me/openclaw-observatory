"""Observatory Monitor — server-rendered instrument panel (Mission M003).

The monitor is the "instrument panel" for the local Observatory deployment:
one HTML page showing OpenClaw agent health, mission progress, host
CPU/RAM/storage, Docker status, and every registered fleet asset with its
computed health — all read from the backend's own registry, mission
projection, and event stream.

Design (SD-020, proposed):

* **Server-rendered HTML from inside the backend** — no React/SPA/build
  toolchain (explicitly out of scope for M003). The backend already owns the
  read models; a separate monitor service would duplicate storage access and
  credentials for zero benefit at this fleet size.
* **Standard library rendering** — string composition + ``html.escape``.
  Every dynamic value is escaped (docs/security.md §9: telemetry text is
  rendered inert, never interpreted).
* **Auto-refresh via ``<meta http-equiv="refresh">``** — no JavaScript
  required; the page is a full read-model snapshot on every load.
* **Exposure** mirrors ``/health`` and ``/metrics`` (SD-013/SD-014): served
  without API-key auth, protected by network boundary (loopback/tailnet
  only). Rationale and trade-offs in SD-020.

This module is split into a *snapshot builder* (async, talks to storage) and
*pure rendering functions* (sync, fully unit-testable without an app).
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.models.mission import MissionRecord
from app.models.registry import AssetType, Connectivity, FleetAssetView, HealthStatus
from app.services.registry import SYSTEM_METRICS_EVENT_TYPE, RegistryService
from app.storage.base import EventStorage, MissionStorage
from app.version import GIT_COMMIT

#: Event types consumed by the monitor beyond the registry read-model.
DOCKER_STATUS_EVENT_TYPE = "docker_status"
AGENT_STATUS_EVENT_TYPE = "agent_status"

#: Page auto-refresh interval (seconds) — meta refresh, no JavaScript.
REFRESH_SECONDS = 10


@dataclass(frozen=True)
class MonitorSnapshot:
    """Everything the monitor page shows, gathered in one pass."""

    generated_at: datetime
    backend_version: str
    backend_fleet_id: str
    backend_uptime_seconds: float
    database_connected: bool
    #: Git commit of the running checkout (deployment traceability,
    #: supervisor review PR 2); ``None`` renders as ``unknown``.
    git_commit: str | None = None
    assets: list[FleetAssetView] = field(default_factory=list)
    missions: list[MissionRecord] = field(default_factory=list)
    host_fleet_id: str | None = None
    host_metrics: dict[str, Any] | None = None
    host_metrics_at: datetime | None = None
    docker: dict[str, Any] | None = None
    agent_fleet_id: str | None = None
    agent_status: dict[str, Any] | None = None
    agent_status_at: datetime | None = None


async def build_snapshot(
    settings: Settings,
    registry: RegistryService,
    missions: MissionStorage,
    events: EventStorage,
    uptime_seconds: float,
    now: datetime | None = None,
) -> MonitorSnapshot:
    """Gather one read-model snapshot for the page (no writes, ever)."""
    now = now or datetime.now(UTC)
    assets = await registry.list_views()
    mission_records = await missions.list_missions()
    db_connected = await events.ping()

    # The host node this deployment runs on: prefer the backend asset's
    # host_fleet_id relationship; fall back to the first registered node.
    backend_view = next(
        (a for a in assets if a.fleet_id == settings.fleet_id), None
    )
    host_id = backend_view.host_fleet_id if backend_view else None
    if host_id is None:
        host_id = next(
            (a.fleet_id for a in assets if a.asset_type is AssetType.NODE), None
        )
    agent_id = next(
        (a.fleet_id for a in assets if a.asset_type is AssetType.AGENT), None
    )

    host_metrics = host_metrics_at = docker = None
    if host_id is not None:
        metrics_event = await events.latest_event(host_id, SYSTEM_METRICS_EVENT_TYPE)
        if metrics_event is not None:
            host_metrics = metrics_event.payload
            host_metrics_at = metrics_event.timestamp
        docker_event = await events.latest_event(host_id, DOCKER_STATUS_EVENT_TYPE)
        if docker_event is not None:
            docker = docker_event.payload

    agent_status = agent_status_at = None
    if agent_id is not None:
        agent_event = await events.latest_event(agent_id, AGENT_STATUS_EVENT_TYPE)
        if agent_event is not None:
            agent_status = agent_event.payload
            agent_status_at = agent_event.timestamp

    return MonitorSnapshot(
        generated_at=now,
        backend_version=settings.app_version,
        backend_fleet_id=settings.fleet_id,
        backend_uptime_seconds=uptime_seconds,
        database_connected=db_connected,
        git_commit=GIT_COMMIT,
        assets=assets,
        missions=mission_records,
        host_fleet_id=host_id,
        host_metrics=host_metrics,
        host_metrics_at=host_metrics_at,
        docker=docker,
        agent_fleet_id=agent_id,
        agent_status=agent_status,
        agent_status_at=agent_status_at,
    )


# --------------------------------------------------------------------- #
# Pure rendering helpers
# --------------------------------------------------------------------- #

def _esc(value: Any) -> str:
    """Escape any value for inert HTML rendering (security.md §9)."""
    return html.escape(str(value), quote=True)


def _dash(value: Any) -> str:
    return _esc(value) if value not in (None, "") else "—"


def _fmt_percent(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.1f}%"
    return "—"


def _fmt_bytes(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "—"
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return "—"  # pragma: no cover - loop always returns


def _fmt_duration(seconds: Any) -> str:
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
        return "—"
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _fmt_age(timestamp: datetime | None, now: datetime) -> str:
    if timestamp is None:
        return "—"
    age = (now - timestamp).total_seconds()
    if age < 0:
        age = 0.0
    return f"{_fmt_duration(age)} ago"


_STATUS_CLASSES = {
    HealthStatus.HEALTHY: "ok",
    HealthStatus.WARNING: "warn",
    HealthStatus.CRITICAL: "crit",
    HealthStatus.OFFLINE: "crit",
    HealthStatus.UNKNOWN: "unknown",
}


def _health_badge(health: HealthStatus) -> str:
    return f'<span class="badge {_STATUS_CLASSES[health]}">{_esc(health.value)}</span>'


def _connectivity_badge(connectivity: Connectivity) -> str:
    css = {
        Connectivity.ONLINE: "ok",
        Connectivity.OFFLINE: "crit",
        Connectivity.UNKNOWN: "unknown",
    }[connectivity]
    return f'<span class="badge {css}">{_esc(connectivity.value)}</span>'


def _bool_badge(value: Any, true_label: str = "yes", false_label: str = "no") -> str:
    if value is True:
        return f'<span class="badge ok">{_esc(true_label)}</span>'
    if value is False:
        return f'<span class="badge crit">{_esc(false_label)}</span>'
    return '<span class="badge unknown">unknown</span>'


# --------------------------------------------------------------------- #
# Section renderers
# --------------------------------------------------------------------- #

def _render_agent_section(snapshot: MonitorSnapshot) -> str:
    status = snapshot.agent_status or {}
    claude = status.get("claude_code") or {}
    rows = [
        ("Agent", _dash(snapshot.agent_fleet_id)),
        ("Status", _dash(status.get("agent_status"))),
        ("Active mission", _dash(status.get("active_mission"))),
        ("Mission state", _dash(status.get("mission_state"))),
        ("Model", _dash(status.get("model"))),
        ("Runtime", _dash(status.get("runtime_version"))),
        (
            "Claude Code",
            _bool_badge(claude.get("available"), "available", "unavailable")
            + (f" {_esc(claude['version'])}" if claude.get("version") else ""),
        ),
        ("Process uptime", _fmt_duration(status.get("process_uptime_seconds"))),
        ("Last completed task", _dash(status.get("last_completed_task"))),
        ("Reported", _fmt_age(snapshot.agent_status_at, snapshot.generated_at)),
        # Token usage placeholder. Intended future ownership (Gate G3 review
        # ruling, docs/M003-open-questions.md §9): the OpenClaw runtime
        # exposes usage in the agent state file, the existing agent collector
        # reports it; Claude API accounting stays a central-side cross-check.
        ("Token usage", '<span class="muted">n/a — not yet collected</span>'),
    ]
    body = "".join(
        f"<tr><th>{_esc(label)}</th><td>{value}</td></tr>" for label, value in rows
    )
    return f'<section><h2>OpenClaw Agent</h2><table class="kv">{body}</table></section>'


def _render_missions_section(snapshot: MonitorSnapshot) -> str:
    if not snapshot.missions:
        rows = '<tr><td colspan="6" class="muted">no missions tracked yet</td></tr>'
    else:
        rows = "".join(
            "<tr>"
            f"<td>{_esc(m.mission_id)}</td>"
            f"<td>{_esc(m.title)}</td>"
            f"<td>{_dash(m.assigned_agent)}</td>"
            f'<td><span class="badge state">{_esc(m.state)}</span></td>'
            f"<td>{_fmt_duration(m.duration_seconds)}</td>"
            f"<td>{_dash(m.pr_ref)}</td>"
            "</tr>"
            for m in snapshot.missions
        )
    return (
        "<section><h2>Missions</h2><table>"
        "<tr><th>ID</th><th>Title</th><th>Agent</th><th>State</th>"
        "<th>Duration</th><th>PR</th></tr>"
        f"{rows}</table></section>"
    )


def _render_host_section(snapshot: MonitorSnapshot) -> str:
    metrics = snapshot.host_metrics or {}
    cpu = metrics.get("cpu") or {}
    memory = metrics.get("memory") or {}
    disk = metrics.get("disk") or {}
    network = metrics.get("network") or {}
    load = " / ".join(
        str(cpu.get(k)) if cpu.get(k) is not None else "—"
        for k in ("load_avg_1m", "load_avg_5m", "load_avg_15m")
    )
    temp = cpu.get("temperature_c")
    rows = [
        ("Host", _dash(snapshot.host_fleet_id)),
        ("CPU utilization", _fmt_percent(cpu.get("utilization_percent"))),
        (
            "CPU temperature",
            f"{temp:.1f} °C" if isinstance(temp, (int, float)) else "—",
        ),
        ("Load average", _esc(load)),
        (
            "RAM",
            f"{_fmt_percent(memory.get('used_percent'))} used "
            f"({_fmt_bytes(memory.get('used_bytes'))} of "
            f"{_fmt_bytes(memory.get('total_bytes'))})",
        ),
        (
            "Disk /",
            f"{_fmt_percent(disk.get('used_percent'))} used "
            f"({_fmt_bytes(disk.get('free_bytes'))} free of "
            f"{_fmt_bytes(disk.get('total_bytes'))})",
        ),
        ("Uptime", _fmt_duration(metrics.get("uptime_seconds"))),
        (
            "Network",
            _bool_badge(network.get("online"), "online", "offline")
            + f" {_dash(network.get('ip_address'))}"
            + (f" ({_esc(network['default_interface'])})"
               if network.get("default_interface") else ""),
        ),
        ("Reported", _fmt_age(snapshot.host_metrics_at, snapshot.generated_at)),
    ]
    body = "".join(
        f"<tr><th>{_esc(label)}</th><td>{value}</td></tr>" for label, value in rows
    )
    return f'<section><h2>Host</h2><table class="kv">{body}</table></section>'


def _render_docker_section(snapshot: MonitorSnapshot) -> str:
    docker = snapshot.docker
    if docker is None:
        return (
            "<section><h2>Docker</h2>"
            '<p class="muted">no docker telemetry received yet</p></section>'
        )
    summary = docker.get("summary") or {}
    header = (
        f"Daemon {_bool_badge(docker.get('daemon_running'), 'running', 'down')} · "
        f"{_esc(summary.get('containers_running', 0))} running / "
        f"{_esc(summary.get('containers_total', 0))} total · "
        f"{_esc(summary.get('containers_failed', 0))} failed · "
        f"{_esc(summary.get('restart_count_total', 0))} restarts"
    )
    containers = docker.get("containers") or []
    if not containers:
        table = ""
    else:
        rows = "".join(
            "<tr>"
            f"<td>{_dash(c.get('name'))}</td>"
            f"<td>{_dash(c.get('image'))}</td>"
            f"<td>{_dash(c.get('status'))}</td>"
            f"<td>{_dash(c.get('restart_count'))}</td>"
            f"<td>{_fmt_percent(c.get('cpu_percent'))}</td>"
            f"<td>{_fmt_percent(c.get('memory_percent'))}</td>"
            "</tr>"
            for c in containers
            if isinstance(c, dict)
        )
        table = (
            "<table><tr><th>Container</th><th>Image</th><th>Status</th>"
            f"<th>Restarts</th><th>CPU</th><th>RAM</th></tr>{rows}</table>"
        )
    return f"<section><h2>Docker</h2><p>{header}</p>{table}</section>"


def _render_fleet_section(snapshot: MonitorSnapshot) -> str:
    if not snapshot.assets:
        rows = '<tr><td colspan="7" class="muted">registry is empty</td></tr>'
    else:
        rows = "".join(
            "<tr>"
            f"<td>{_esc(a.fleet_id)}</td>"
            f"<td>{_esc(a.asset_type.value)}</td>"
            f"<td>{_esc(a.role)}</td>"
            f"<td>{_connectivity_badge(a.connectivity)}</td>"
            f"<td>{_health_badge(a.health)}</td>"
            f"<td>{_fmt_age(a.last_heartbeat.timestamp if a.last_heartbeat else None, snapshot.generated_at)}</td>"
            f"<td>{_dash(a.last_heartbeat.collector_version if a.last_heartbeat else None)}</td>"
            "</tr>"
            for a in snapshot.assets
        )
    return (
        "<section><h2>Fleet &amp; Services</h2><table>"
        "<tr><th>Fleet ID</th><th>Type</th><th>Role</th><th>Connectivity</th>"
        "<th>Health</th><th>Last heartbeat</th><th>Collector</th></tr>"
        f"{rows}</table></section>"
    )


_STYLE = """
:root { color-scheme: dark; }
body { font-family: ui-monospace, 'DejaVu Sans Mono', monospace; margin: 1.5rem;
       background: #101418; color: #d7dde3; }
h1 { font-size: 1.25rem; margin: 0 0 0.25rem; }
h2 { font-size: 1rem; border-bottom: 1px solid #2a343e;
     padding-bottom: 0.25rem; margin: 1.25rem 0 0.5rem; }
table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
th, td { text-align: left; padding: 0.25rem 0.6rem 0.25rem 0; vertical-align: top; }
table.kv th { width: 12rem; color: #8fa1b3; font-weight: normal; }
tr + tr td, tr + tr th { border-top: 1px solid #1d242c; }
.badge { padding: 0.05rem 0.45rem; border-radius: 0.6rem; font-size: 0.8rem; }
.badge.ok { background: #123d24; color: #6fd58a; }
.badge.warn { background: #4a3a10; color: #e7c25b; }
.badge.crit { background: #4a1616; color: #ef8a8a; }
.badge.unknown { background: #2a343e; color: #8fa1b3; }
.badge.state { background: #16324a; color: #7bb8ea; }
.muted { color: #66788a; }
.meta { color: #66788a; font-size: 0.8rem; margin-bottom: 0.5rem; }
"""


def _active_mission_label(snapshot: MonitorSnapshot) -> str:
    """Active mission for the header: agent-reported first, projection second.

    The agent's own status report is the freshest signal; when it is absent
    (e.g. the agent collector is down) fall back to the newest non-Completed
    mission in the backend's projection. ``none`` when neither knows one.
    """
    status = snapshot.agent_status or {}
    mission = status.get("active_mission")
    if mission:
        state = status.get("mission_state")
        return f"{_esc(mission)} ({_esc(state)})" if state else _esc(mission)
    for record in reversed(snapshot.missions):
        if record.state != "Completed":
            return f"{_esc(record.mission_id)} ({_esc(record.state)})"
    return "none"


def render_monitor_html(snapshot: MonitorSnapshot) -> str:
    """Render the full monitor page (pure function of the snapshot)."""
    db_badge = _bool_badge(snapshot.database_connected, "connected", "unreachable")
    commit = _esc(snapshot.git_commit[:12]) if snapshot.git_commit else "unknown"
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        f'<meta http-equiv="refresh" content="{REFRESH_SECONDS}">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Observatory Monitor</title>"
        f"<style>{_STYLE}</style></head><body>"
        "<h1>OpenClaw Observatory — Monitor</h1>"
        # Deployment identification (supervisor review, PR 2): version,
        # commit, and active mission up front so troubleshooting starts
        # from exactly which software is running on this host.
        f'<p class="meta">{_esc(snapshot.backend_fleet_id)} '
        f"v{_esc(snapshot.backend_version)} · commit {commit} · "
        f"mission {_active_mission_label(snapshot)} · database {db_badge} · "
        f"backend up {_fmt_duration(snapshot.backend_uptime_seconds)} · "
        f"generated {_esc(snapshot.generated_at.strftime('%Y-%m-%d %H:%M:%S %Z'))} · "
        f"auto-refresh {REFRESH_SECONDS}s</p>"
        f"{_render_agent_section(snapshot)}"
        f"{_render_missions_section(snapshot)}"
        f"{_render_host_section(snapshot)}"
        f"{_render_docker_section(snapshot)}"
        f"{_render_fleet_section(snapshot)}"
        "</body></html>"
    )
