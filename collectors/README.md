# Collectors

Push-based telemetry producers (SD-002) for the OpenClaw Observatory,
introduced by Mission M003. They submit events to the backend's authenticated
REST API (`POST /api/v1/events`, SD-004/SD-017) and are deliberately
**standard-library only** — no third-party dependencies on fleet hosts
(SD-019, proposed).

| Collector | Module | Events | Mission scope |
| --- | --- | --- | --- |
| Raspberry Pi host | `observatory_collectors.host_pi` | `heartbeat`, `system_metrics`, `docker_status` | M003 §2/§10 |
| OpenClaw agent | `observatory_collectors.openclaw_agent` | `heartbeat`, `agent_status`, `mission_update` | M003 §3/§4 |

Both collectors are installed and running on RPSG01 as systemd user units
(M003 PR 2, supervisor-authorized) — see “Deployment on RPSG01” below.

## Running

```bash
cd collectors
# configuration via environment (see config.example.env)
export FLEET_ID=RPSG01 OBSERVATORY_API_KEY=... OBSERVATORY_URL=http://127.0.0.1:8000

python3 -m observatory_collectors.host_pi --once     # one cycle, then exit
python3 -m observatory_collectors.host_pi            # loop (heartbeat + telemetry)

python3 -m observatory_collectors.openclaw_agent --once
```

Requires Python ≥ 3.11 (the OS python3 on RPSG01 is fine). No `pip install`
needed. Docker telemetry uses the `docker` CLI and requires the collector
user in the `docker` group.

## Configuration (M003 §8)

| Variable | Default | Meaning |
| --- | --- | --- |
| `OBSERVATORY_URL` | `http://127.0.0.1:8000` | Backend base URL (tailnet address in production, SD-003) |
| `FLEET_ID` | — (required) | This collector's Fleet Registry identity |
| `OBSERVATORY_API_KEY` / `_FILE` | — (required) | API key bound to `FLEET_ID` (SD-017) |
| `COLLECTOR_NAME` | per collector | Human-readable collector name (User-Agent) |
| `HEARTBEAT_INTERVAL` | `30` | Seconds between heartbeats |
| `TELEMETRY_INTERVAL` | = heartbeat | Seconds between telemetry snapshots |
| `MISSION_POLL_INTERVAL` | `60` | Seconds between mission-state polls (agent collector) |
| `REQUEST_TIMEOUT` | `10` | HTTP timeout seconds |
| `MAX_RETRIES` | `3` | Retries for transient delivery failures (backoff, max 30s) |

Agent-collector extras: `AGENT_STATE_FILE`, `AGENT_PROCESS_PATTERN`,
`AGENT_MODEL_ID` (see `observatory_collectors/openclaw_agent/collector.py`).

## Agent state file

The OpenClaw agent runtime maintains a small JSON document the collector
reads (it never writes):

```json
{
  "agent_status": "active",
  "active_mission": "M003",
  "mission_state": "EXECUTING",
  "last_completed_task": "M002 merged",
  "model": "anthropic/claude-fable-5",
  "missions": [
    {"mission_id": "M003", "title": "Observatory Self-Awareness",
     "state": "Running", "assigned_agent": "A001"}
  ]
}
```

Entries under `missions` are forwarded as `mission_update` events —
deduplicated client-side, so only actual transitions reach the backend
(which validates lifecycle order and rejects illegal moves with 409).

**Backfill rule:** the first time the collector observes a mission that is
already mid-flight (any state other than `Created`), it stamps
`backfill: true` on that initial `mission_update` — the backend only admits
entry at a non-initial state as a privileged, audit-logged backfill
transition (mission lifecycle rules, docs/M003-open-questions.md §5/§7).
Subsequent observations follow the normal one-step graph without the flag.
An explicit `backfill` value in the state file is passed through untouched
(operator-driven recovery jumps).

## Deployment on RPSG01 (as executed, M003 PR 2)

systemd **user** units are provided in [`systemd/`](systemd/); the backend
and ClickHouse units live in [`../deploy/systemd/`](../deploy/systemd/).
Enabling them is an infrastructure change requiring supervisor approval
(AGENTS.md §12) — granted for RPSG01 in M003 PR 2. The exact steps executed:

```bash
# 1. Untracked configuration (secrets never enter the repository)
mkdir -p ~/.config/observatory ~/.config/systemd/user
#    one key per identity (SD-017), e.g.: openssl rand -hex 32
cp collectors/config.example.env ~/.config/observatory/host-collector.env   # edit: FLEET_ID=RPSG01 + key
cp collectors/config.example.env ~/.config/observatory/agent-collector.env  # edit: FLEET_ID=A001 + key,
                                                                            # AGENT_STATE_FILE, AGENT_MODEL_ID
chmod 600 ~/.config/observatory/*.env
# backend.env gets the matching API_KEYS bindings (see ../deploy/backend.example.env)

# 2. Agent state file (maintained by the agent runtime; collector only reads)
#    ~/.config/observatory/agent-state.json — shape documented above

# 3. Units
cp collectors/systemd/*.service deploy/systemd/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now observatory-clickhouse observatory-backend
systemctl --user enable --now observatory-host-collector observatory-agent-collector
loginctl enable-linger $USER    # keep user units running without a session
```

Validation: `curl -s http://127.0.0.1:8000/health`, then
`GET /api/v1/fleet` (authenticated) shows RPSG01/A001 online with live
telemetry, and `http://127.0.0.1:8000/monitor` renders the instrument panel.
The sandboxing directives (`ProtectHome=read-only`, `ProtectSystem=strict`,
`NoNewPrivileges`, `PrivateTmp`) run as-written under systemd 257 user
units on Raspberry Pi OS.

## Failure behavior

- Delivery failures are retried with exponential backoff (transient errors
  only); the collector keeps running when the Observatory is down.
- Probe failures degrade to `null` fields, never crash the loop.
- All failures are counted and self-reported in heartbeats
  (`failures_total`), which feeds the backend health score (M003 §9) and the
  `observatory_collector_reported_failures` metric.

## Tests

```bash
cd collectors
python3 -m pytest
```

Fully offline: parsers are tested with canned `/proc`/CLI fixtures and the
client with a fake opener.
