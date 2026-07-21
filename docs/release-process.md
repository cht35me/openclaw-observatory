# Release Process — OpenClaw Observatory

Operational release, deployment, and rollback discipline (Mission M003.5 §7,
Phase 2.1). Strategy and environment topology live in
[deployment.md](deployment.md); this document is the checklist you actually run.

## 1. How a Change Ships

```text
feature branch → PR (template) → CI green (required) → human review/approval
              → merge to main → tag vX.Y.Z → deploy → verify → (rollback path ready)
```

- `main` only changes through reviewed PRs; merges require human approval
  ([MISSION.md](../MISSION.md), [ENGINEERING_PRINCIPLES.md](../ENGINEERING_PRINCIPLES.md) §4–5).
- Branch protection on `main` **requires** the CI checks below plus one approving
  review; force pushes and deletions are disabled; branches must be up to date
  with `main` before merge (strict status checks).

## 2. Required CI Checks

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs on every PR and
push to `main`. All four job names are required status-check contexts:

| Check (context) | What it proves |
| --- | --- |
| `Backend unit tests` | Full backend pytest suite (offline, in-memory storage) on Python 3.13 |
| `Collector tests` | Stdlib-only collector suite (SD-019) |
| `ClickHouse integration tests` | Storage layer against a real pinned `clickhouse-server` (a skip fails the job) |
| `Ruff lint & format` | `ruff check` + `ruff format --check` over `backend/app backend/tests collectors` |

Branch protection was applied via:

```bash
gh api -X PUT repos/cht35me/openclaw-observatory/branches/main/protection \
  --input branch-protection.json   # strict checks + 1 review, no force push/delete
```

with `required_status_checks.contexts` exactly matching the four job names above.
Changing a job name in `ci.yml` **must** be mirrored in branch protection in the
same change, or merges will deadlock on a phantom context.

## 3. Release Checklist (before tagging)

- [ ] All mission PRs merged to `main`; CI green on the merge commit.
- [ ] Tests pass locally on the deployment host (backend + collectors suites).
- [ ] Documentation updated in the same PRs that changed behavior.
- [ ] No secrets in the diff; `.example` files still hold placeholders only.
- [ ] Migrations (if any) are append-only and one-step backward compatible
      ([ENGINEERING_PRINCIPLES.md](../ENGINEERING_PRINCIPLES.md) §10).
- [ ] Version chosen (semver-ish `v0.x.y`, §6) and release notes drafted
      (PR links + one-line summary per change).

## 4. Deployment Checklist (RPSG01 native units; VPS compose at Phase 4)

Scripted since Phase 2.1: **`deploy/scripts/upgrade.sh <tag>`** performs the
steps below (with config validation before any restart and a recorded
rollback target); see [deploy/README.md](../deploy/README.md). Manually:

- [ ] Record the currently deployed tag/commit (`/monitor` header or
      `git -C <deploy checkout> rev-parse HEAD`) — this is the rollback target
      (the script records it in `~/.config/observatory/deploy-state`).
- [ ] Apply configuration changes (untracked `~/.config/observatory/*.env`);
      set `APP_VERSION` to the tag (§6) **before** upgrading.
- [ ] Fetch and check out the release tag in the deployment checkout.
- [ ] Dependencies: `backend/.venv/bin/pip install -r backend/requirements.txt`
      (pinned; dev extras are not installed on deployment hosts).
- [ ] Validate configuration against the new release *before* restarting
      (`validate_all_config` in the scripts; the services also fail fast on
      their own — [deployment.md](deployment.md) §12).
- [ ] Restart units: `systemctl --user restart observatory-backend` (ClickHouse
      and collectors only when their artifacts changed).
- [ ] Verify: `/health` returns `ok`, `/monitor` header shows the expected
      version + commit, a fresh heartbeat arrives, no errors in
      `journalctl --user -u observatory-backend -n 50`.

## 5. Rollback Checklist

Scripted since Phase 2.1: **`deploy/scripts/rollback.sh [tag]`** (defaults to
the recorded previous deployment). Manually:

- [ ] Check out the previous release tag (recorded in §4, step 1).
- [ ] Reinstall pinned requirements if they differed between tags.
- [ ] Restore `APP_VERSION` to the previous tag; restart the affected units.
- [ ] Verify exactly as in §4 (health, monitor header commit, heartbeats).
- [ ] Migrations are append-only ClickHouse DDL: schema created by the newer
      release is tolerated by the older one. If a change ever breaks this,
      its PR must say so and ship a tested down-migration **before** deploy
      ([deployment.md](deployment.md) §8).
- [ ] Report the rollback and its cause to the supervisor (Telegram; §15
      failure-reporting principles).

## 6. Release Tagging

- Tags are semver-ish **`v0.x.y`** annotated tags on `main`, created after merge:
  `git tag -a v0.2.0 -m "M003.5: CI + release discipline" && git push origin v0.2.0`.
  First release so tagged: **`v0.2.0`** (M003.5 PR 1 + PR 2 merge commit).
- **Minor** (`v0.x.0`): each merged mission/PR batch that changes behavior.
  **Patch** (`v0.x.y`): fixes to an already-tagged release. `v1.0.0` is deferred
  until the Phase 4 production deployment.
- **The deployed `APP_VERSION` equals the tag** (e.g. `APP_VERSION=v0.2.0` in the
  backend env file). `/health`, `/metrics`, and the `/monitor` header report it.
- The `/monitor` header's **git commit** (auto-detected, or `GIT_COMMIT` env in
  image builds — [backend/app/version.py](../backend/app/version.py)) must match
  the tagged commit: `git rev-list -n1 v0.2.0`. Version says what was *intended*;
  commit proves what is *running*.

## 7. Decisions (M003.5 PR 1)

Recorded here as release-engineering notes; the supervisor may promote any of
them to `docs/decisions/SD-NNN` records.

- **Ruff adopted** (pinned `ruff==0.15.22` in
  [backend/requirements-dev.txt](../backend/requirements-dev.txt)) as the single
  lint + format tool. Configuration in the repository-root
  [pyproject.toml](../pyproject.toml): rules `E, F, I, W, UP, B`, line length 100
  (the prevailing style: code sat at ~88–100 columns), target `py313`, formatter
  at defaults. Root placement lets one config govern `backend/` and `collectors/`.
  The initial `ruff format` pass was mechanical line-joining only (33 files,
  no logic changes).
- **Static typing deferred.** mypy/pyright are *not* adopted in Phase 2.1: the
  codebase is fully annotated and Pydantic validates at runtime boundaries, so a
  checker's marginal value today does not justify the CI time and stub-tuning
  cost. Revisit at a later milestone (candidate: Phase 3, when the API surface
  grows a frontend consumer) — the mission spec lists type checking as optional.
- **Required CI checks** are the four contexts in §2, applied to `main` branch
  protection together with: strict up-to-date requirement, 1 approving review,
  `enforce_admins` off, no force pushes, no deletions.

---

Related: [deployment.md](deployment.md) · [security.md](security.md) ·
[roadmap.md](roadmap.md) · [../MISSION.md](../MISSION.md) ·
[../.github/pull_request_template.md](../.github/pull_request_template.md)
