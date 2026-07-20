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

Environment (beyond the shared M003 §8 variables):

* ``AGENT_STATE_FILE`` — JSON status document maintained by the agent;
* ``AGENT_PROCESS_PATTERN`` — pgrep pattern for the agent process
  (default ``openclaw``);
* ``AGENT_MODEL_ID`` — fallback model identifier when the state file has none.
"""

from __future__ import annotations

import argparse
import logging
import os
from typing import Any

from observatory_collectors.client import ObservatoryClient
from observatory_collectors.config import CollectorConfig
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
    ) -> None:
        self._state_file = state_file
        self._process_pattern = process_pattern
        self._model_fallback = model_fallback
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
            "claude_code": probes.probe_claude_code(),
            "runtime_version": probes.probe_runtime_version(),
            "process_uptime_seconds": probes.probe_process_uptime(
                self._process_pattern
            ),
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
            events.append(("mission_update", update, MISSION_UPDATE_SCHEMA))
            self._submitted_states[mission_id] = mission_state
        return events


def software_version() -> str | None:
    return probes.probe_runtime_version()


def build_runner(config: CollectorConfig, env: dict[str, str] | None = None) -> CollectorRunner:
    env = dict(os.environ) if env is None else env
    client = ObservatoryClient(config)
    telemetry = AgentTelemetry(
        state_file=env.get("AGENT_STATE_FILE") or None,
        process_pattern=env.get("AGENT_PROCESS_PATTERN", "openclaw"),
        model_fallback=env.get("AGENT_MODEL_ID") or None,
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
        software_version_fn=software_version,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Observatory OpenClaw agent collector")
    parser.add_argument(
        "--once", action="store_true", help="run all tasks once and exit"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    config = CollectorConfig.from_env(default_collector_name="openclaw-agent")
    runner = build_runner(config)
    if args.once:
        submitted = runner.run_once()
        logging.getLogger("collector").info("submitted %d event(s)", submitted)
        return 0 if submitted > 0 else 1
    runner.run_forever()
    return 0  # pragma: no cover - run_forever does not return
