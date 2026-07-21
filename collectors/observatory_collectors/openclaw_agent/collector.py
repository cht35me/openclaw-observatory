"""OpenClaw agent collector assembly (Mission M003 §3/§4).

Produces:

* ``heartbeat`` — liveness + versioning (shared runner);
* ``agent_status`` — agent status, active mission + state, Claude Code
  availability, runtime version, model identifier, process uptime, last
  completed task;
* ``mission_update`` — forwarded from the agent state file's ``missions``
  list at ``MISSION_POLL_INTERVAL``, deduplicated client-side (an unchanged
  mission state is not resubmitted, keeping the event stream to actual
  transitions).

Backfill rule (M003 open question 5, PR 2 note): the first time this
collector observes a mission that is already mid-flight (any state other
than ``Created``), it stamps ``backfill: true`` on that initial
``mission_update`` — the backend only admits entry at a non-initial state
(or a forward jump) as a privileged, audit-logged backfill transition.
Subsequent observations follow the normal one-step lifecycle graph and are
forwarded without the flag (unless the state file explicitly sets it, e.g.
for operator-driven recovery jumps).

Environment (beyond the shared M003 §8 variables):

* ``AGENT_STATE_FILE`` — JSON status document maintained by the agent;
* ``AGENT_PROCESS_PATTERN`` — pgrep pattern for the agent process
  (default ``openclaw``);
* ``AGENT_MODEL_ID`` — fallback model identifier when the state file has none;
* ``CLAUDE_BIN`` / ``OPENCLAW_BIN`` — explicit executable paths for the CLI
  probes (M003.6 §1); unset falls back to PATH discovery. Parsed by
  :class:`CollectorConfig` because systemd user units run with a minimal
  PATH that misses per-user installs.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any

from observatory_collectors.client import ObservatoryClient
from observatory_collectors.config import CollectorConfig, ConfigError
from observatory_collectors.openclaw_agent import probes
from observatory_collectors.runner import CollectorRunner, EventTuple, Task

COLLECTOR_TYPE = "openclaw-agent"

AGENT_STATUS_SCHEMA = 1
MISSION_UPDATE_SCHEMA = 1


class AgentTelemetry:
    """agent_status + deduplicated mission_update producer."""

    def __init__(
        self,
        state_file: str | None,
        process_pattern: str = "openclaw",
        model_fallback: str | None = None,
        claude_bin: str | None = None,
        openclaw_bin: str | None = None,
    ) -> None:
        self._state_file = state_file
        self._process_pattern = process_pattern
        self._model_fallback = model_fallback
        self._claude_bin = claude_bin
        self._openclaw_bin = openclaw_bin
        #: mission_id -> last submitted state (client-side dedup).
        self._submitted_states: dict[str, str] = {}

    # -- agent_status ---------------------------------------------------- #

    def produce_status(self) -> list[EventTuple]:
        state = probes.read_state_file(self._state_file)
        payload: dict[str, Any] = {
            "agent_status": state.get("agent_status", "unknown"),
            "active_mission": state.get("active_mission"),
            "mission_state": state.get("mission_state"),
            "last_completed_task": state.get("last_completed_task"),
            "model": state.get("model") or self._model_fallback,
            "claude_code": probes.probe_claude_code(self._claude_bin),
            "runtime_version": probes.probe_runtime_version(self._openclaw_bin),
            "process_uptime_seconds": probes.probe_process_uptime(self._process_pattern),
        }
        return [("agent_status", payload, AGENT_STATUS_SCHEMA)]

    # -- mission_update forwarding ---------------------------------------- #

    def produce_mission_updates(self) -> list[EventTuple]:
        state = probes.read_state_file(self._state_file)
        events: list[EventTuple] = []
        for update in state.get("missions", []):
            mission_id = update.get("mission_id")
            mission_state = update.get("state")
            if not isinstance(mission_id, str) or not isinstance(mission_state, str):
                continue
            if self._submitted_states.get(mission_id) == mission_state:
                continue  # no transition since last poll
            payload = dict(update)
            if (
                mission_id not in self._submitted_states
                and mission_state != "Created"
                and not payload.get("backfill")
            ):
                # First sync of an in-flight mission: privileged entry at a
                # non-initial state must be an explicit, audit-logged
                # backfill (mission lifecycle rules, M003 open question 5).
                payload["backfill"] = True
            events.append(("mission_update", payload, MISSION_UPDATE_SCHEMA))
            self._submitted_states[mission_id] = mission_state
        return events


def software_version(openclaw_bin: str | None = None) -> str | None:
    return probes.probe_runtime_version(openclaw_bin)


def build_runner(config: CollectorConfig, env: dict[str, str] | None = None) -> CollectorRunner:
    env = dict(os.environ) if env is None else env
    client = ObservatoryClient(config)
    telemetry = AgentTelemetry(
        state_file=env.get("AGENT_STATE_FILE") or None,
        process_pattern=env.get("AGENT_PROCESS_PATTERN", "openclaw"),
        model_fallback=env.get("AGENT_MODEL_ID") or None,
        claude_bin=config.claude_bin,
        openclaw_bin=config.openclaw_bin,
    )
    tasks = [
        Task("agent_status", config.telemetry_interval, telemetry.produce_status),
        Task(
            "mission_updates",
            config.mission_poll_interval,
            telemetry.produce_mission_updates,
        ),
    ]
    return CollectorRunner(
        config,
        client,
        tasks,
        collector_type=COLLECTOR_TYPE,
        software_version_fn=lambda: software_version(config.openclaw_bin),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Observatory OpenClaw agent collector")
    parser.add_argument("--once", action="store_true", help="run all tasks once and exit")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        # Fail fast, before any collection starts (M003.5 §2): a clear
        # one-line error beats a traceback in the journal.
        config = CollectorConfig.from_env(default_collector_name="openclaw-agent")
    except ConfigError as exc:
        print(f"observatory-agent-collector: configuration error: {exc}", file=sys.stderr)
        return 2
    runner = build_runner(config)
    if args.once:
        submitted = runner.run_once()
        logging.getLogger("collector").info("submitted %d event(s)", submitted)
        return 0 if submitted > 0 else 1
    runner.run_forever()
    return 0  # pragma: no cover - run_forever does not return
