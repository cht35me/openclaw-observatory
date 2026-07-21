<!-- PR title: "M00X[.Y] PR n: <summary>" — see MISSION.md. -->

## Mission / Scope

- **Mission:** M0XX — <mission title> (PR n of m)
- **Scope:** <which mission items this PR delivers; what is deliberately excluded>

## What Changed

- <focused summary of the change, grouped by area>

## Validation

<!-- ENGINEERING_PRINCIPLES.md §13: every PR states what was validated and how. -->

- **Backend tests:** `cd backend && .venv/bin/python -m pytest` → <N passed>
- **Collector tests:** `cd backend && .venv/bin/python -m pytest ../collectors` → <N passed>
- **Ruff:** `ruff check` + `ruff format --check` over `backend/app backend/tests collectors` → <clean / findings fixed>
- **Other:** <manual verification, integration evidence, screenshots>

## Checklist

- [ ] Docs updated in this PR ([ENGINEERING_PRINCIPLES.md](../ENGINEERING_PRINCIPLES.md) §2)
- [ ] Decision records (`docs/decisions/SD-NNN`) added/updated, or none needed
- [ ] [docs/release-process.md](../docs/release-process.md) checklists respected
- [ ] No secrets or sensitive identifiers in any commit
- [ ] Diff contains only mission-related changes

## Open Questions / Judgment Calls

- <non-material decisions made autonomously, per MISSION.md Clarification stage>
