"""Observatory Monitor — server-rendered instrument panel (Mission M003).

The monitor is the "instrument panel" for the local Observatory deployment:
one HTML page showing OpenClaw agent health, mission progress, host
CPU/RAM/storage, Docker status, and every registered fleet asset with its
computed health — all read from the backend's own registry, mission
projection, and event stream.

Design (SD-020, accepted at Gate G3 review):

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
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import Settings
from app.models.event import Event
from app.models.mission import MissionRecord
from app.models.registry import AssetType, Connectivity, FleetAssetView, HealthStatus
from app.services.offline import OFFLINE_EVENT_TYPE, ONLINE_EVENT_TYPE
from app.services.pipeline import MISSION_UPDATE_EVENT_TYPE
from app.services.registry import SYSTEM_METRICS_EVENT_TYPE, RegistryService
from app.services.startup_event import SERVICE_START_EVENT_TYPE
from app.storage.base import EventStorage, HostInventoryStorage, MissionStorage
from app.version import BUILD_TIMESTAMP, GIT_COMMIT

#: Event types consumed by the monitor beyond the registry read-model.
DOCKER_STATUS_EVENT_TYPE = "docker_status"
AGENT_STATUS_EVENT_TYPE = "agent_status"

#: Page auto-refresh interval (seconds) — meta refresh, no JavaScript.
REFRESH_SECONDS = 10

#: Recent Events cap (M003.5 §4) — one bounded query, keeps the page fast.
RECENT_EVENTS_LIMIT = 20

#: Event types shown in Recent Events. Heartbeats are deliberately
#: EXCLUDED (judgment call, docs/M003.5-notes.md): at a 30-second cadence
#: they would fill all 20 slots within minutes and drown every actually
#: notable event; heartbeat *absence* is already surfaced as offline/online
#: transitions. Collector failures likewise arrive as heartbeat counters
#: (no discrete event exists), visible through the health score instead.
NOTABLE_EVENT_TYPES: tuple[str, ...] = (
    SERVICE_START_EVENT_TYPE,
    OFFLINE_EVENT_TYPE,
    ONLINE_EVENT_TYPE,
    MISSION_UPDATE_EVENT_TYPE,
)


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
    #: Build timestamp (M003.5 §6): committer timestamp of the deployed
    #: commit, or the BUILD_TIMESTAMP override; ``None`` renders ``unknown``.
    build_timestamp: str | None = None
    #: Deployment environment classification (M003.5 §3e/§6).
    deployment_environment: str = "Development"
    assets: list[FleetAssetView] = field(default_factory=list)
    missions: list[MissionRecord] = field(default_factory=list)
    host_fleet_id: str | None = None
    host_metrics: dict[str, Any] | None = None
    host_metrics_at: datetime | None = None
    host_inventory: dict[str, Any] | None = None
    host_inventory_at: datetime | None = None
    docker: dict[str, Any] | None = None
    agent_fleet_id: str | None = None
    agent_status: dict[str, Any] | None = None
    agent_status_at: datetime | None = None
    recent_events: list[Event] = field(default_factory=list)


async def build_snapshot(
    settings: Settings,
    registry: RegistryService,
    missions: MissionStorage,
    events: EventStorage,
    inventories: HostInventoryStorage,
    uptime_seconds: float,
    now: datetime | None = None,
) -> MonitorSnapshot:
    """Gather one read-model snapshot for the page (no writes, ever).

    Performance gate G3.5 (refresh < 1 s): every read here is bounded —
    latest-row reads (registry FINAL, newest event per type) plus one
    LIMIT-20 recent-events query.
    """
    now = now or datetime.now(UTC)
    assets = await registry.list_views()
    mission_records = await missions.list_missions()
    db_connected = await events.ping()

    # The host node this deployment runs on: prefer the backend asset's
    # host_fleet_id relationship; fall back to the first registered node.
    backend_view = next((a for a in assets if a.fleet_id == settings.fleet_id), None)
    host_id = backend_view.host_fleet_id if backend_view else None
    if host_id is None:
        host_id = next((a.fleet_id for a in assets if a.asset_type is AssetType.NODE), None)
    agent_id = next((a.fleet_id for a in assets if a.asset_type is AssetType.AGENT), None)

    host_metrics = host_metrics_at = docker = None
    host_inventory = host_inventory_at = None
    if host_id is not None:
        metrics_event = await events.latest_event(host_id, SYSTEM_METRICS_EVENT_TYPE)
        if metrics_event is not None:
            host_metrics = metrics_event.payload
            host_metrics_at = metrics_event.timestamp
        docker_event = await events.latest_event(host_id, DOCKER_STATUS_EVENT_TYPE)
        if docker_event is not None:
            docker = docker_event.payload
        inventory_record = await inventories.get_inventory(host_id)
        if inventory_record is not None:
            host_inventory = inventory_record.payload
            host_inventory_at = inventory_record.reported_at

    recent = await events.query_events(event_types=NOTABLE_EVENT_TYPES, limit=RECENT_EVENTS_LIMIT)

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
        build_timestamp=BUILD_TIMESTAMP,
        deployment_environment=settings.deployment_environment.value,
        assets=assets,
        missions=mission_records,
        host_fleet_id=host_id,
        host_metrics=host_metrics,
        host_metrics_at=host_metrics_at,
        host_inventory=host_inventory,
        host_inventory_at=host_inventory_at,
        docker=docker,
        agent_fleet_id=agent_id,
        agent_status=agent_status,
        agent_status_at=agent_status_at,
        recent_events=recent,
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


def _fmt_used(used_bytes: Any, used_percent: Any) -> str:
    """Actual usage + percentage, e.g. ``6.2 GiB (28.0%)`` (M003.5 monitor)."""
    if used_bytes is None and used_percent is None:
        return "—"
    return f"{_fmt_bytes(used_bytes)} ({_fmt_percent(used_percent)})"


def _fmt_installed_memory(total_bytes: Any) -> str:
    """Installed memory as marketed capacity (§3a example: ``4 GB``).

    Physical RAM minus firmware reservations is what ``MemTotal`` reports;
    rounding to the nearest decimal GB recovers the module size.
    """
    if not isinstance(total_bytes, (int, float)) or isinstance(total_bytes, bool):
        return "—"
    gigabytes = total_bytes / 1_000_000_000
    if gigabytes >= 1:
        return f"{round(gigabytes)} GB"
    return _fmt_bytes(total_bytes)


def _fmt_last_reboot(uptime_seconds: Any, now: datetime) -> str:
    """Humanized boot moment (§3-monitor): ``Today/Yesterday HH:MM`` or
    ``N days ago``, derived from uptime. Timestamps are UTC (matching the
    page's ``generated`` stamp)."""
    if not isinstance(uptime_seconds, (int, float)) or isinstance(uptime_seconds, bool):
        return "—"
    booted = now - timedelta(seconds=float(uptime_seconds))
    days = (now.date() - booted.date()).days
    if days <= 0:
        return f"Today {booted.strftime('%H:%M')}"
    if days == 1:
        return f"Yesterday {booted.strftime('%H:%M')}"
    return f"{days} days ago"


def _fmt_epoch_age(epoch: Any, now: datetime) -> str:
    if not isinstance(epoch, (int, float)) or isinstance(epoch, bool):
        return "—"
    return _fmt_age(datetime.fromtimestamp(float(epoch), tz=UTC), now)


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
        # Token usage: architecture ruled and documented (M003.5 §5,
        # docs/token-usage-architecture.md) — the OpenClaw runtime owns the
        # numbers, the agent collector transports them as an agent_status
        # field, Claude API accounting stays a central-side cross-check.
        (
            "Token usage",
            '<span class="muted">n/a — runtime-owned, agent collector transport '
            "(docs/token-usage-architecture.md)</span>",
        ),
    ]
    body = "".join(f"<tr><th>{_esc(label)}</th><td>{value}</td></tr>" for label, value in rows)
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


def _render_system_section(snapshot: MonitorSnapshot) -> str:
    """System summary (M003.5 §3-monitor): hardware + OS identity, uptime."""
    inventory = snapshot.host_inventory or {}
    hardware = inventory.get("hardware") or {}
    os_info = inventory.get("os") or {}
    maintenance = inventory.get("maintenance") or {}
    metrics = snapshot.host_metrics or {}
    uptime = metrics.get("uptime_seconds")

    model = hardware.get("model")
    if model and hardware.get("revision"):
        model_cell = f"{_esc(model)} (rev {_esc(hardware['revision'])})"
    else:
        model_cell = _dash(model)
    cpu_bits = [
        part
        for part in (
            hardware.get("cpu_model"),
            hardware.get("cpu_architecture"),
            f"{hardware['cpu_cores']} cores" if hardware.get("cpu_cores") else None,
        )
        if part
    ]
    os_name = os_info.get("name")
    os_cell = (
        f"{_esc(os_name)} {_esc(os_info['release'])}"
        if os_name and os_info.get("release")
        else _dash(os_name)
    )
    rows = [
        ("Manufacturer", _dash(hardware.get("manufacturer"))),
        ("Hardware model", model_cell),
        ("CPU", _esc(" · ".join(cpu_bits)) if cpu_bits else "—"),
        ("Installed memory", _fmt_installed_memory(hardware.get("memory_total_bytes"))),
        ("Operating system", os_cell),
        ("Kernel", _dash(os_info.get("kernel"))),
        ("Hostname", _dash(os_info.get("hostname"))),
        ("Uptime", _fmt_duration(uptime)),
        ("Last reboot", _esc(_fmt_last_reboot(uptime, snapshot.generated_at))),
        # Maintenance status (§3d): spot systems needing attention fast.
        (
            "Last apt update",
            _fmt_epoch_age(maintenance.get("last_apt_update_epoch"), snapshot.generated_at),
        ),
        ("Last full-upgrade", _dash(maintenance.get("last_apt_full_upgrade"))),
        ("Updates available", _dash(maintenance.get("updates_available"))),
        (
            "Reboot required",
            _bool_badge(maintenance.get("reboot_required"), "required", "no")
            if "reboot_required" in maintenance
            else "—",
        ),
    ]
    if not inventory:
        note = '<p class="muted">no host inventory received yet</p>'
    else:
        note = ""
    body = "".join(f"<tr><th>{_esc(label)}</th><td>{value}</td></tr>" for label, value in rows)
    return f'<section><h2>System</h2>{note}<table class="kv">{body}</table></section>'


def _render_storage_section(snapshot: MonitorSnapshot) -> str:
    """Structured storage inventory (§3b) with single-disk fallback."""
    inventory = snapshot.host_inventory or {}
    devices = inventory.get("storage") or []
    if not devices:
        # Graceful fallback: the pre-M003.5 single-disk line from
        # system_metrics, until the collector reports an inventory event.
        disk = (snapshot.host_metrics or {}).get("disk") or {}
        if not disk:
            return (
                "<section><h2>Storage</h2>"
                '<p class="muted">no storage inventory received yet</p></section>'
            )
        line = (
            f"Disk {_esc(disk.get('path', '/'))}: "
            f"{_fmt_used(disk.get('used_bytes'), disk.get('used_percent'))} used, "
            f"{_fmt_bytes(disk.get('free_bytes'))} free of {_fmt_bytes(disk.get('total_bytes'))}"
        )
        return f"<section><h2>Storage</h2><p>{line}</p></section>"
    rows = "".join(
        "<tr>"
        f"<td>{_dash(d.get('name'))}</td>"
        f"<td>{_dash(d.get('type'))}</td>"
        f"<td>{_dash(d.get('transport'))}</td>"
        f"<td>{_fmt_bytes(d.get('capacity_bytes'))}</td>"
        f"<td>{_dash(d.get('brand'))}</td>"
        f"<td>{_dash(d.get('mount'))}</td>"
        f"<td>{_dash(d.get('filesystem'))}</td>"
        f"<td>{_fmt_used(d.get('used_bytes'), d.get('used_percent'))}</td>"
        f"<td>{_fmt_bytes(d.get('free_bytes'))}</td>"
        "</tr>"
        for d in devices
        if isinstance(d, dict)
    )
    return (
        "<section><h2>Storage</h2><table>"
        "<tr><th>Device</th><th>Type</th><th>Transport</th><th>Size</th>"
        "<th>Brand</th><th>Mount</th><th>FS</th><th>Used</th><th>Free</th></tr>"
        f"{rows}</table></section>"
    )


def _render_interfaces_section(snapshot: MonitorSnapshot) -> str:
    """Interfaces + default route (M003.5 §3-monitor)."""
    network = (snapshot.host_inventory or {}).get("network") or {}
    interfaces = network.get("interfaces") or []
    if not interfaces:
        return (
            "<section><h2>Interfaces</h2>"
            '<p class="muted">no interface inventory received yet</p></section>'
        )
    rows = "".join(
        "<tr>"
        f"<td>{_dash(i.get('name'))}</td>"
        f"<td>{_dash(i.get('ipv4'))}</td>"
        f"<td>{_link_state_badge(i.get('link_state'))}</td>"
        "</tr>"
        for i in interfaces
        if isinstance(i, dict)
    )
    table = f"<table><tr><th>Interface</th><th>IPv4</th><th>Link</th></tr>{rows}</table>"
    route = network.get("default_route") or {}
    if route:
        route_line = (
            f"<p>Default route: {_dash(route.get('gateway'))} "
            f"dev {_dash(route.get('interface'))}</p>"
        )
    else:
        route_line = '<p class="muted">no default route</p>'
    return f"<section><h2>Interfaces</h2>{table}{route_line}</section>"


def _link_state_badge(state: Any) -> str:
    state_text = str(state or "unknown").lower()
    css = {"up": "ok", "down": "crit"}.get(state_text, "unknown")
    return f'<span class="badge {css}">{_esc(state_text.upper())}</span>'


def _event_detail(event: Event) -> str:
    """One-line, fully escaped summary for a Recent Events row."""
    payload = event.payload or {}
    if event.event_type == MISSION_UPDATE_EVENT_TYPE:
        mission = payload.get("mission_id", "?")
        state = payload.get("state", "?")
        detail = f"{mission} → {state}"
        if payload.get("backfill"):
            detail += " (backfill)"
        return _esc(detail)
    if event.event_type in (OFFLINE_EVENT_TYPE, ONLINE_EVENT_TYPE):
        return _esc(f"{payload.get('previous', '?')} → {payload.get('current', '?')}")
    if event.event_type == SERVICE_START_EVENT_TYPE:
        commit = payload.get("git_commit")
        commit_text = str(commit)[:12] if commit else "unknown"
        return _esc(f"v{payload.get('version', '?')} · commit {commit_text}")
    return _esc(str(payload)[:120])  # pragma: no cover - defensive default


def _render_recent_events_section(snapshot: MonitorSnapshot) -> str:
    """Recent Events (M003.5 §4): last 20 notable events, newest first."""
    if not snapshot.recent_events:
        rows = '<tr><td colspan="4" class="muted">no notable events yet</td></tr>'
    else:
        rows = "".join(
            "<tr>"
            f"<td>{_fmt_age(e.timestamp, snapshot.generated_at)}</td>"
            f"<td>{_esc(e.collector_id)}</td>"
            f'<td><span class="badge state">{_esc(e.event_type)}</span></td>'
            f"<td>{_event_detail(e)}</td>"
            "</tr>"
            for e in snapshot.recent_events
        )
    return (
        f"<section><h2>Recent Events (last {RECENT_EVENTS_LIMIT})</h2>"
        "<table><tr><th>When</th><th>Asset</th><th>Event</th><th>Detail</th></tr>"
        f"{rows}</table>"
        '<p class="muted">heartbeats are summarized as offline/online '
        "transitions, not listed individually</p></section>"
    )


def _render_host_section(snapshot: MonitorSnapshot) -> str:
    metrics = snapshot.host_metrics or {}
    cpu = metrics.get("cpu") or {}
    memory = metrics.get("memory") or {}
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
            "Network",
            _bool_badge(network.get("online"), "online", "offline")
            + f" {_dash(network.get('ip_address'))}"
            + (
                f" ({_esc(network['default_interface'])})"
                if network.get("default_interface")
                else ""
            ),
        ),
        ("Reported", _fmt_age(snapshot.host_metrics_at, snapshot.generated_at)),
    ]
    body = "".join(f"<tr><th>{_esc(label)}</th><td>{value}</td></tr>" for label, value in rows)
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
            f"<td>{_dash(c.get('network_mode'))}</td>"
            f"<td>{_fmt_duration(c.get('uptime_seconds'))}</td>"
            f"<td>{_fmt_percent(c.get('cpu_percent'))}</td>"
            f"<td>{_fmt_percent(c.get('memory_percent'))}</td>"
            f"<td>{_fmt_bytes(c.get('network_rx_bytes'))}</td>"
            f"<td>{_fmt_bytes(c.get('network_tx_bytes'))}</td>"
            f"<td>{_dash(c.get('restart_count'))}</td>"
            "</tr>"
            for c in containers
            if isinstance(c, dict)
        )
        # M003.5 §3-monitor: Network / Uptime / RX / TX / Restarts columns
        # for container diagnosis.
        table = (
            "<table><tr><th>Container</th><th>Image</th><th>Status</th>"
            "<th>Network</th><th>Uptime</th><th>CPU</th><th>RAM</th>"
            f"<th>RX</th><th>TX</th><th>Restarts</th></tr>{rows}</table>"
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
            f"<td>{_fmt_age(a.last_heartbeat.timestamp if a.last_heartbeat else None, snapshot.generated_at)}</td>"  # noqa: E501
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


def _collector_versions_label(snapshot: MonitorSnapshot) -> str:
    """Collector versions from the newest heartbeats (M003.5 header).

    The backend's own service asset is excluded — its \"collector\" is the
    backend itself, already identified by the version at the front of the
    header line.
    """
    parts = [
        f"{_esc(a.fleet_id)} v{_esc(a.last_heartbeat.collector_version)}"
        for a in snapshot.assets
        if a.fleet_id != snapshot.backend_fleet_id
        and a.last_heartbeat is not None
        and a.last_heartbeat.collector_version
    ]
    return ", ".join(parts) if parts else "none reporting"


def render_monitor_html(snapshot: MonitorSnapshot) -> str:
    """Render the full monitor page (pure function of the snapshot)."""
    db_badge = _bool_badge(snapshot.database_connected, "connected", "unreachable")
    commit = _esc(snapshot.git_commit[:12]) if snapshot.git_commit else "unknown"
    built = _esc(snapshot.build_timestamp) if snapshot.build_timestamp else "unknown"
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        f'<meta http-equiv="refresh" content="{REFRESH_SECONDS}">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Observatory Monitor</title>"
        f"<style>{_STYLE}</style></head><body>"
        "<h1>OpenClaw Observatory — Monitor</h1>"
        # Deployment identification (supervisor review, PR 2; extended with
        # build & release metadata, M003.5 §6): version, commit, build
        # timestamp, environment, active mission, and collector versions up
        # front so troubleshooting starts from exactly which software is
        # running on this host.
        f'<p class="meta">{_esc(snapshot.backend_fleet_id)} '
        f"v{_esc(snapshot.backend_version)} · commit {commit} · "
        f"built {built} · env {_esc(snapshot.deployment_environment)} · "
        f"mission {_active_mission_label(snapshot)} · "
        f"collectors {_collector_versions_label(snapshot)} · "
        f"database {db_badge} · "
        f"backend up {_fmt_duration(snapshot.backend_uptime_seconds)} · "
        f"generated {_esc(snapshot.generated_at.strftime('%Y-%m-%d %H:%M:%S %Z'))} · "
        f"auto-refresh {REFRESH_SECONDS}s</p>"
        f"{_render_agent_section(snapshot)}"
        f"{_render_missions_section(snapshot)}"
        f"{_render_system_section(snapshot)}"
        f"{_render_host_section(snapshot)}"
        f"{_render_storage_section(snapshot)}"
        f"{_render_interfaces_section(snapshot)}"
        f"{_render_docker_section(snapshot)}"
        f"{_render_fleet_section(snapshot)}"
        f"{_render_recent_events_section(snapshot)}"
        "</body></html>"
    )
