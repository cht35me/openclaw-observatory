# MISSION.md — Mission Lifecycle and Governance

This document defines the reusable mission lifecycle for all autonomous-agent work in
this repository and, by extension, the fleet. Agent behavior rules live in
[AGENTS.md](AGENTS.md); engineering values live in
[ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md).

## Mission ID Format

Missions use sequential, zero-padded identifiers:

```text
M001
M002
M003
```

- IDs are globally unique across the fleet and never reused.
- IDs appear in branch names (lowercase, e.g., `a001/m001-observatory-foundation`),
  PR titles (e.g., `M001: establish OpenClaw Observatory foundation`), and mission records.
- If mission volume ever exceeds three digits, the format extends naturally (`M1000`);
  padding is a readability convention, not a hard limit.
- **Point-release missions** (supervisor-introduced with M003.5, Phase 2.1) append a
  single dotted numeric suffix to an existing mission ID: `M003.5`. They denote
  supervisor-inserted follow-up milestones between planned missions. Exactly one
  suffix level is allowed (`M003.5.1` is invalid), and the suffix carries no ordering
  semantics in tooling — point IDs are plain, unique mission identifiers
  (pattern: `^M[0-9]{3,}(\.[0-9]+)?$`).

## Mission Assignment

- Missions are assigned by the supervisor through the engineering interface (SSH).
- A mission assignment includes: mission ID, assigned agent, objective, scope,
  deliverables, constraints, and success criteria.
- An agent works on one active mission at a time unless explicitly instructed otherwise.
- Unassigned work is out of scope; agents may *propose* missions but not self-assign.

### Mission Acceptance Response (required)

When accepting a mission or supervisor instruction, the agent always responds in this
format before starting work:

```text
- Mission received.
- Estimated complexity:
- Estimated duration:
- Execution plan:
- Starting now...
```

### Supervisor Decisions

- Supervisor decisions are marked **SD-NNN**, where NNN is an integer sequence.
- Every decision is recorded as `docs/decisions/SD-NNN-name.md` (NAME = decision
  subject) in the same PR that acts on it. See
  [docs/decisions/](docs/decisions/README.md).

## Mission States

```text
ASSIGNED → PLANNING → (CLARIFICATION) → EXECUTING → VALIDATING
        → PR_OPEN → IN_REVIEW → APPROVED → COMPLETED

Any active state may transition to: BLOCKED, PAUSED, FAILED, or CANCELLED.
BLOCKED/PAUSED return to the state they interrupted once resolved.
```

| State | Meaning |
| --- | --- |
| ASSIGNED | Mission received; not yet started |
| PLANNING | Agent reviews the specification and plans the work |
| CLARIFICATION | Agent has paused to ask the supervisor a blocking question |
| EXECUTING | Agent performs the work on a dedicated feature branch |
| VALIDATING | Agent verifies its own work against the specification |
| PR_OPEN | Pull Request opened; supervisor notified |
| IN_REVIEW | Human review in progress; agent responds to feedback |
| APPROVED | Supervisor approved; merge authorized by a human |
| COMPLETED | Merged (or otherwise accepted); mission summary delivered |
| BLOCKED | External impediment prevents progress |
| PAUSED | Supervisor or agent intentionally suspended work |
| FAILED | Mission cannot meet its success criteria |
| CANCELLED | Supervisor withdrew the mission |

## Lifecycle Stages

### 1. Planning Stage

- Read the full mission specification and the current repository state.
- Identify deliverables, constraints, out-of-scope items, and success criteria.
- Identify ambiguities that materially affect the outcome.
- Confirm a clean working tree and create the feature branch from the latest `main`.

### 2. Clarification Stage (conditional)

- If a material ambiguity exists, pause before executing.
- Ask the supervisor via Telegram: the decision needed, why, the recommended option,
  alternatives, and consequences.
- Do not proceed on assumptions. Minor, non-material choices may be made autonomously
  and documented in the PR under "Open questions" or "Decisions".

### 3. Execution Stage

- Work only on the dedicated feature branch.
- Make small, focused commits with clear messages.
- Stay strictly within mission scope; new ideas become proposals, not scope creep.
- Follow all rules in [AGENTS.md](AGENTS.md).

### 4. Validation Stage

Before opening a PR, verify:

- All deliverables exist and match the specification.
- Internal consistency: naming, links, cross-references.
- No secrets or sensitive identifiers in any commit.
- The diff against `main` contains only mission-related changes.
- Any available validation tooling (linters, link checkers, tests) has been run,
  without introducing unnecessary dependencies.

### 5. Pull Request Stage

- Push the branch and open a PR against `main` with a clear title (`M00X: <summary>`).
- The PR description includes: mission summary, files created/changed, key decisions,
  open questions, risks, validation performed, and a statement of whether production
  code is included.
- Notify the supervisor via Telegram with the PR URL and a concise summary.

### 6. Human Review Stage

- Wait. Respond to review comments with fixes or reasoned discussion.
- Additional commits during review stay on the same branch and within scope.
- Never merge, approve your own PR, or dismiss reviews.

### 7. Approval Stage

- **Human approval is mandatory before any merge. No exceptions.**
- Approval authority rests with the supervisor (or a human delegate they name).
- Approval of a documentation/architecture mission does not authorize implementation;
  implementation requires its own mission.

### 8. Completion Stage

- After merge (performed by a human, or by the agent only if explicitly instructed
  post-approval), the agent delivers a **mission summary**: what was delivered, key
  decisions, deviations from the specification, follow-up recommendations, and links
  (PR, commits).
- Mission state becomes COMPLETED. Local branch cleanup only after the supervisor
  confirms it is safe.

## Blocked and Paused States

- **BLOCKED:** progress is impossible (missing access, failing dependency, unanswered
  material question). Escalate once via Telegram with the blocker and options, then wait.
- **PAUSED:** work is intentionally suspended (by supervisor instruction or agent
  judgment, e.g., suspected security issue).
- In both states, the agent performs **safe stopping** ([AGENTS.md §10](AGENTS.md)):
  preserve branch work, push if possible, leave a clean tree, record state, take no
  further external action.

## Definition of Done

A mission is Done when all of the following hold:

1. All specified deliverables are complete and pushed on the feature branch.
2. Validation has been performed and documented.
3. A Pull Request was opened with a complete description.
4. The supervisor was notified.
5. A human reviewed and approved the PR.
6. The PR was merged by or under the authority of a human.
7. A mission summary was delivered.

## Definition of Failed

A mission is Failed when its success criteria cannot be met — e.g., the specification
proves infeasible, a hard technical or security constraint emerges, or the supervisor
rejects the approach without a revised specification. On failure the agent: performs safe
stopping, reports honestly what failed and why, and proposes next steps. Failure is
reported, never hidden.

## Definition of Cancelled

A mission is Cancelled when the supervisor withdraws it before completion. The agent
performs safe stopping, preserves all work for possible resumption, and confirms
cancellation. Cancelled work is deleted only on explicit supervisor instruction.

## Mission Summary Requirement

Every mission that reaches COMPLETED, FAILED, or CANCELLED ends with a written summary
covering: outcome, deliverables, decisions and trade-offs, deviations, open questions,
and recommended follow-up missions. Summaries are delivered through the PR description
and/or the engineering interface, with a concise Telegram notice for completion.

---

Defined under Mission M001 by A001-OC01-RPSG01. Changes require supervisor approval.
