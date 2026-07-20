# SD-019 — Collectors Are Standard-Library-Only Python

- **Status:** Proposed (final wording for Gate G3 approval)
- **Date:** 2026-07-20
- **Proposed by:** A001-OC01-RPSG01 (Mission M003)
- **Context:** M003 delivers the first production collectors (Raspberry Pi
  host, OpenClaw agent) running directly on fleet hosts under systemd — the
  deployable collector utility ships in M003 PR 2 (branch
  `a001/m003-collectors-monitor`). The backend has a pinned virtualenv
  (FastAPI/Pydantic, SD-011), but collectors deploy to hosts where
  maintaining per-collector virtualenvs and dependency updates multiplies
  operational surface across a growing fleet.

## Decision

**Fleet-host collectors use only the Python standard library (Python ≥ 3.11,
the OS `python3` on Raspberry Pi OS Bookworm). No `pip install` ever runs on
a fleet host.** HTTP uses `urllib.request`; metrics come from `/proc`,
`/sys`, `os`, `shutil`, and platform CLIs (`docker`, `ip`) invoked through
`subprocess` with fixed argument lists.

## Consequences

- Deployment is `git pull` + systemd unit — no virtualenv lifecycle, no
  dependency CVE tracking, no ARM wheel-building on the Pi.
- No `requests`/`psutil` conveniences: host metrics are read from
  `/proc`/`/sys` directly, which ties the host collector to Linux. That is
  acceptable — fleet hosts are Linux by definition (FLEET.md platforms).
- Parsing logic must be tested against captured fixtures (done in the
  collector test suite) since no third-party library abstracts it.
- The wire contract stays one-sided: the backend validates payload schemas
  (`heartbeat`, `mission_update`, …) with Pydantic server-side; collectors
  emit plain JSON and never share code with the backend.
- If a future collector genuinely needs a third-party dependency (e.g. a
  vendor SDK), that collector proposes a superseding/refining decision; the
  default for new collectors remains stdlib-only.

## Related

[SD-002](SD-002-push-based-collectors.md) ·
[SD-011](SD-011-python-backend.md) ·
M003 PR 2 branch `a001/m003-collectors-monitor` (collectors/ package)
