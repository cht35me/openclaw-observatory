"""Mission tracking models (Mission M003 §4).

Mission lifecycle (linear, forward-only):

    Created → Queued → Assigned → Running → Review → Completed

**Permitted transition graph** (exact, supervisor-ruled at Gate G3 review):

*Normal operation* follows the explicit lifecycle graph — with states
indexed ``Created=0 … Completed=5``, a reported transition
``current → new`` is legal iff it is a **self-loop** (idempotent metadata
refresh of ``pr_ref``/``commit_sha``) or the **single next step**
(``index(new) == index(current) + 1``):

* ``Created``  → Created | Queued
* ``Queued``   → Queued | Assigned
* ``Assigned`` → Assigned | Running
* ``Running``  → Running | Review
* ``Review``   → Review | Completed
* ``Completed``→ Completed (terminal; repeats refresh metadata only)

A mission unknown to the backend enters at ``Created`` in normal operation.

*Privileged backfill/recovery* (``backfill: true`` on the
:class:`MissionUpdate` payload, audit-logged) may **enter at any state** for
an unknown mission (missions predating tracking, e.g. M001/M002) or **jump
forward** over intermediate states (``index(new) >= index(current)``) for
recovery after reporting gaps.

In *both* modes: **regression is rejected with 409** — review findings are
represented by staying in ``Review`` until the rework lands, not by moving
backwards — and **Completed remains terminal**.

**Observed state, not canonical records:** transitions arrive as
``mission_update`` telemetry events through the normal authenticated
ingestion path. Collectors *report observed mission state*; they cannot
authoritatively create or mutate canonical mission records — the canonical
mission definition lives with the supervisor's mission documents, and the
backend's :class:`MissionRecord` store is a *validated projection* of the
observed event stream (which remains the durable, auditable transition
record).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

#: Mission IDs per MISSION.md: ``M001``, ``M002``, … (padding is convention),
#: plus supervisor-introduced point releases such as ``M003.5`` (Phase 2.1).
#: Point IDs are plain strings — no ordering semantics attach to the suffix.
MissionId = Annotated[str, Field(pattern=r"^M[0-9]{3,}(\.[0-9]+)?$")]

ShortText = Annotated[str, Field(max_length=256)]

#: Ordered lifecycle states. Index encodes ordering for transition checks.
MISSION_STATES: tuple[str, ...] = (
    "Created",
    "Queued",
    "Assigned",
    "Running",
    "Review",
    "Completed",
)

_STATE_INDEX = {state: index for index, state in enumerate(MISSION_STATES)}


def is_valid_transition(current: str | None, new: str, *, backfill: bool = False) -> bool:
    """Return whether ``current → new`` is a legal lifecycle move.

    Normal operation (``backfill=False``):

    * an unknown mission may only enter the lifecycle at ``Created``;
    * a known mission may repeat its current state (idempotent metadata
      refresh) or advance exactly one step along the lifecycle;
    * skipping intermediate states is **not** permitted.

    Privileged backfill/recovery (``backfill=True``, audit-logged at the
    ingestion pipeline):

    * an unknown mission may enter at any state (import of missions that
      predate tracking);
    * a known mission may jump forward over intermediate states (recovery
      after reporting gaps).

    In both modes regression is rejected and ``Completed`` is terminal
    (only its self-loop remains legal).
    """
    if new not in _STATE_INDEX:
        return False
    if current is None:
        return True if backfill else new == MISSION_STATES[0]
    if current not in _STATE_INDEX:
        return False
    delta = _STATE_INDEX[new] - _STATE_INDEX[current]
    if backfill:
        return delta >= 0
    return delta in (0, 1)


class MissionUpdate(BaseModel):
    """Validated payload of a ``mission_update`` telemetry event."""

    model_config = ConfigDict(extra="forbid")

    mission_id: MissionId
    title: ShortText
    state: str = Field(description="Target lifecycle state.")
    assigned_agent: ShortText | None = Field(
        default=None, description="Fleet ID of the assigned agent (e.g. A001)."
    )
    pr_ref: ShortText | None = Field(
        default=None, description="Pull Request reference (e.g. cht35me/repo#3)."
    )
    commit_sha: ShortText | None = None
    note: ShortText | None = None
    backfill: bool = Field(
        default=False,
        description=(
            "Privileged backfill/recovery transition: permits entering the "
            "lifecycle at any state or jumping forward over intermediate "
            "states. Never permits regression; Completed stays terminal. "
            "Usage is audit-logged."
        ),
    )


class MissionRecord(BaseModel):
    """Current-state projection of one mission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: str
    title: str
    assigned_agent: str | None
    state: str
    created_at: datetime
    started_at: datetime | None = Field(
        default=None, description="Set when the mission first enters Running."
    )
    completed_at: datetime | None = Field(
        default=None, description="Set when the mission enters Completed."
    )
    pr_ref: str | None
    commit_sha: str | None
    updated_at: datetime

    @property
    def duration_seconds(self) -> float | None:
        """Elapsed Running→Completed duration, when both ends are known."""
        if self.started_at is None or self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()


class MissionView(BaseModel):
    """Read-model returned by the missions API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: str
    title: str
    assigned_agent: str | None
    state: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: float | None
    pr_ref: str | None
    commit_sha: str | None
    updated_at: datetime

    @classmethod
    def from_record(cls, record: MissionRecord) -> MissionView:
        return cls(
            mission_id=record.mission_id,
            title=record.title,
            assigned_agent=record.assigned_agent,
            state=record.state,
            created_at=record.created_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
            duration_seconds=record.duration_seconds,
            pr_ref=record.pr_ref,
            commit_sha=record.commit_sha,
            updated_at=record.updated_at,
        )
