"""OpenClaw agent probe tests (M003 §3/§4)."""

from __future__ import annotations

import json

from observatory_collectors.openclaw_agent import probes
from observatory_collectors.openclaw_agent.collector import AgentTelemetry

STATE = {
    "agent_status": "active",
    "active_mission": "M003",
    "mission_state": "EXECUTING",
    "last_completed_task": "M002 merged",
    "model": "anthropic/claude-fable-5",
    "missions": [
        {"mission_id": "M003", "title": "Observatory Self-Awareness",
         "state": "Running", "assigned_agent": "A001"},
    ],
}


def test_state_document_parsing_is_defensive() -> None:
    parsed = probes.parse_state_document(json.dumps(STATE))
    assert parsed["agent_status"] == "active"
    assert parsed["active_mission"] == "M003"
    assert len(parsed["missions"]) == 1

    assert probes.parse_state_document("not json") == {}
    assert probes.parse_state_document('["list"]') == {}
    # Non-string fields and oversized values are dropped/bounded.
    weird = probes.parse_state_document(
        json.dumps({"agent_status": 42, "model": "x" * 2000, "missions": "nope"})
    )
    assert "agent_status" not in weird
    assert len(weird["model"]) == 512
    assert "missions" not in weird


def test_proc_stat_starttime_parsing() -> None:
    # comm contains spaces and parentheses — the classic trap.
    stat = "1234 (tricky name) with) S 1 1234 1234 0 -1 4194560 " + " ".join(
        str(n) for n in range(10, 26)
    )
    ticks = probes.parse_starttime_ticks(stat)
    # Fixture values equal their field numbers (10..25), so field 22 == 22.
    assert ticks == 22
    assert probes.parse_starttime_ticks("short) 1 2") is None


def test_process_uptime_computation() -> None:
    assert probes.process_uptime_seconds(100, 1000.0, 100) == 999.0
    assert probes.process_uptime_seconds(None, 1000.0, 100) is None
    assert probes.process_uptime_seconds(100, None, 100) is None
    assert probes.process_uptime_seconds(200_000, 1000.0, 100) is None  # negative


def test_mission_updates_deduplicated(tmp_path) -> None:
    state_file = tmp_path / "agent-state.json"
    state_file.write_text(json.dumps(STATE), encoding="utf-8")
    telemetry = AgentTelemetry(state_file=str(state_file))

    first = telemetry.produce_mission_updates()
    assert len(first) == 1
    assert first[0][0] == "mission_update"
    assert first[0][1]["state"] == "Running"

    # Unchanged state -> no resubmission.
    assert telemetry.produce_mission_updates() == []

    # Transition -> submitted again.
    STATE_DONE = dict(STATE)
    STATE_DONE["missions"] = [{**STATE["missions"][0], "state": "Completed"}]
    state_file.write_text(json.dumps(STATE_DONE), encoding="utf-8")
    second = telemetry.produce_mission_updates()
    assert len(second) == 1
    assert second[0][1]["state"] == "Completed"


def test_agent_status_payload_shape(tmp_path) -> None:
    state_file = tmp_path / "agent-state.json"
    state_file.write_text(json.dumps(STATE), encoding="utf-8")
    telemetry = AgentTelemetry(state_file=str(state_file), model_fallback="fallback")

    events = telemetry.produce_status()
    assert len(events) == 1
    event_type, payload, schema = events[0]
    assert event_type == "agent_status"
    assert payload["agent_status"] == "active"
    assert payload["active_mission"] == "M003"
    assert payload["mission_state"] == "EXECUTING"
    assert payload["model"] == "anthropic/claude-fable-5"  # state beats fallback
    assert "claude_code" in payload and "available" in payload["claude_code"]
    assert "runtime_version" in payload
    assert "process_uptime_seconds" in payload


def test_agent_status_without_state_file() -> None:
    telemetry = AgentTelemetry(state_file=None, model_fallback="fallback-model")
    payload = telemetry.produce_status()[0][1]
    assert payload["agent_status"] == "unknown"
    assert payload["model"] == "fallback-model"
