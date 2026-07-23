# Deployment Strategy — OpenClaw Observatory

Status: **Strategy (§1–§11) plus the operational RPSG01 package (§12,
Phase 2.1).** The VPS staging/production topology remains future work
(Phase 4); the RPSG01 native deployment is live and scripted.

## 1. Deployment Lifecycle Overview

```text
Develop (Raspberry Pi SG01)
   │  feature branch → Pull Request
   ▼
GitHub (review, human approval, merge to main)
   │  tested artifact / tagged release
   ▼
VPS Staging (soak, verification)
   │  human approval
   ▼
VPS Production (monitored, backed up, rollback-ready)
   ▲
   └── Distributed collectors connect from remote hosts over the tailnet
```

1. **Development on Raspberry Pi SG01:** agents develop on feature branches in local
   clones; local runs and tests only — the Pi never serves production traffic.
2. **GitHub feature branches and Pull Requests:** every change reaches `main` only
   through a reviewed PR ([AGENTS.md](../AGENTS.md)).
3. **Human review and merge:** supervisor approval is the release gate; merges are
   performed by or under the authority of a human ([MISSION.md](../MISSION.md)).
4. **Testing:** unit/integration tests run before PR locally **and** in CI
   ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml), Phase 2.1): backend,
   collector, and ClickHouse integration suites plus Ruff are required status checks on
   `main` — see [release-process.md](release-process.md). A change without stated
   validation does not ship.
5. **VPS staging deployment:** merged code deploys first to a staging instance on the
   VPS (separate containers/ports/data), soaks with real-but-noncritical telemetry, and
   is verified against a checklist.
6. **Production deployment on VPS:** after explicit human approval, the same artifact
   (not a rebuild) is promoted to production.
7. **Distributed collectors:** remote hosts (RPSG01 first, later hosts as commissioned)
   run collectors that push to production over the tailnet with per-collector
   credentials.
8. **Monitoring and rollback:** production is monitored from deploy time; a documented,
   rehearsed rollback path exists for every release.

## 2. Environment Separation

| Environment | Where | Purpose | Data |
| --- | --- | --- | --- |
| Development | Pi SG01 (and future dev hosts) | build and test changes | synthetic/local |
| Staging | VPS (isolated containers) | pre-production verification | non-critical/mirrored |
| Production | VPS | the real Observatory | fleet data, backed up |

- Environments never share databases, credentials, or tokens.
- Staging is configured identically to production except size, secrets, and endpoints.
- Environment-specific behavior comes from configuration, never from code branches.

## 3. Configuration Management

- All configuration in version control as `*.example` templates with placeholders;
  real values injected per environment (env vars / host-local files).
- One configuration mechanism across environments; differences are values, not shapes.
- Configuration changes to production follow the same review path as code.
- Deployment-identity variables (M003.5 §3e/§6):
  - `DEPLOYMENT_ENVIRONMENT` — backend; `Production | Staging | Development |
    Test` (exact values), default `Development`. Shown on the monitor header
    and stamped into `service_start` events; production deployments must set
    it explicitly.
  - `BUILD_TIMESTAMP` — backend, optional; overrides the detected commit
    timestamp in packaged/container builds (defaults to
    `git log -1 --format=%cI` of the running checkout, else `unknown`).
  - `INVENTORY_INTERVAL` — host collector; host-inventory re-report cadence
    in seconds (default `3600`; inventory is also sent on start and on
    durable change).

## 4. Secrets Management

- Secrets are never in Git, images, or logs ([security.md](security.md) §5).
- Injected at deploy time via environment variables or host-local files with tight
  permissions; a dedicated secret manager is a future upgrade if secret count grows.
- Separate secrets per environment; staging compromise must not expose production.
- Rotation procedures documented alongside each credential's issuance record.

## 5. Container-Based Deployment

**Recommendation:** Docker (or compatible) containers orchestrated with Compose on the
VPS.

- **Why:** reproducible artifacts, clean separation of staging/production on one VPS,
  restart policies for free, easy rollback by image tag, and the fleet's scale does not
  justify Kubernetes-class orchestration.
- **Trade-offs:** image hygiene and update discipline become part of operations.
- **Alternatives:** systemd services from release tarballs (simpler runtime, weaker
  isolation/reproducibility); Kubernetes/Nomad (unjustified operational weight at this
  scale); Podman as a drop-in Docker alternative (worth evaluating at implementation).

Images: official, version-pinned bases; built from the repository; tagged with release
version + commit; staging and production run the *same image*.

## 6. Backups

- Automated scheduled backups of the production database and configuration; at least one
  copy stored off the VPS.
- Backup restore is **exercised** on staging at Phase 4 and periodically thereafter
  ([roadmap.md](roadmap.md)) — an untested backup is a hope, not a backup.
- Retention: enough history to recover from slow-burn corruption, not just crashes
  (e.g., daily for 14 days + weekly for 8 weeks as a starting point; finalize at Phase 4).

## 7. Updates

- **Application:** release-tagged, staged-then-promoted, never edited in place.
- **OS/runtime:** unattended security patches where safe (host OS); container base
  images refreshed deliberately via rebuild PRs.
- **Dependencies:** upgraded through reviewed PRs with pinned versions
  ([security.md](security.md) §8).
- Update windows are irrelevant at current scale but recorded in logs for correlation.

## 8. Rollback

- Every production deploy records: previous image tag, database schema version, config
  version.
- Rollback = redeploy previous image tag; database migrations must be
  backward-compatible one step or ship with a tested down-migration
  ([ENGINEERING_PRINCIPLES.md](../ENGINEERING_PRINCIPLES.md) §10).
- If rollback is impossible for a given change, that fact is declared in the PR and
  requires explicit supervisor acknowledgment before deploy.

## 9. Health Checks, Logging, and Metrics

- **Health:** liveness/readiness endpoints consumed by container restart policies and
  external monitoring; the deploy process verifies health before declaring success.
- **Logging:** structured JSON logs with rotation/retention; secret-free by policy;
  shipped/aggregated in a later phase if needed.
- **Metrics:** the Observatory exposes its own `/metrics` (Prometheus-compatible) from
  MVP — self-observability is a launch feature, not an afterthought
  ([vision.md](vision.md)).

## 10. Network Security

- All Observatory traffic (collectors, dashboard, SSH) rides the private tailnet
  (Tailscale or equivalent); **no Observatory ports are exposed publicly.**
- VPS firewall is default-deny on the public interface; SSH is key-only and
  tailnet-preferred.
- Per-collector credentials + tailnet identity provide two independent authentication
  layers for ingestion.
- Details and alternatives (WireGuard, mTLS): [security.md](security.md) §6 and
  [architecture.md](architecture.md) §2.3.

## 11. Production Hardening Checklist (to satisfy before/at Phase 4)

- [ ] Default-deny firewall verified on public interface
- [ ] SSH: key-only, no root login, tailnet-restricted where feasible
- [ ] Automatic security updates on host OS
- [ ] Containers run as non-root with minimal images
- [ ] Secrets present only in runtime environment, never in images or Git
- [ ] Per-collector tokens issued and individually revocable
- [ ] Backups running and restore rehearsed
- [ ] Health checks wired to restart policy
- [ ] Structured logging with retention configured
- [ ] `/metrics` exposed and scraped/watched
- [ ] Rollback rehearsed on staging
- [ ] Incident-response runbook reachable and current ([security.md](security.md) §12)

## 12. RPSG01 Native Deployment Package (Phase 2.1)

Mission M003.5 §2 delivered a scripted lifecycle for the current native
deployment (systemd user units on RPSG01). Full runbook:
[deploy/README.md](../deploy/README.md).

- **Install / upgrade / rollback / uninstall:**
  [deploy/scripts/](../deploy/scripts/) — idempotent install (never overwrites
  real config), upgrade to a release tag with recorded rollback target
  (`~/.config/observatory/deploy-state`), rollback to the recorded previous
  deployment, conservative uninstall (unit files and config are moved aside,
  never deleted; ClickHouse data untouched).
- **Configuration validation before startup (fail fast):** the backend
  (`uvicorn --factory app.main:build_app` → `app.config.load_settings()`)
  and both collectors (`CollectorConfig.from_env()`) reject
  missing/invalid/placeholder configuration with one clear, secret-free
  error and exit code 2 **before binding or collecting**. The deploy scripts
  run the same validation before restarting anything, so a bad upgrade
  leaves the running services untouched.
- **Automatic service startup:** all four units are `enabled` and
  `loginctl enable-linger` is on (verified live in PR 3), so the stack
  starts at boot with no login session.

### Persistent journald (host prerequisite, M003.6 §2)

Debian defaults to `Storage=auto`: with no `/var/log/journal/<machine-id>`
directory the journal is **volatile** (`/run/log/journal`, lost on reboot)
and — crucially for a dedicated service user — unreadable: the runtime
directory is mode `2750 root:systemd-journal` with an ACL for group `adm`
only, so `journalctl --user` fails with *"No journal files were opened due
to insufficient permissions"* even for the user's **own** journal (the
directory is not traversable). Post-reboot forensics are impossible on top
of that, because the previous boot's logs are gone.

> **Raspberry Pi OS (Trixie) caveat:** the OS ships a vendor drop-in
> `/usr/lib/systemd/journald.conf.d/40-rpi-volatile-storage.conf` with
> `Storage=volatile`, which **overrides** the `Storage=auto` default. On
> such hosts, creating `/var/log/journal` alone does **nothing** — journald
> stays volatile. You must add an admin drop-in that sorts *after* the
> vendor one (verified live on this fleet's Pi, 2026-07-22).

Enable persistent journald **once per host** (requires sudo; this is the
least-privilege fix — do *not* add the service user to `adm` or
`systemd-journal`, which would expose every other unit's logs).

**Step 1 — override any vendor `Storage=` drop-in** (required on Raspberry
Pi OS Trixie; harmless elsewhere). Create
`/etc/systemd/journald.conf.d/60-observatory-persistent.conf`:

```ini
[Journal]
Storage=persistent
SystemMaxUse=200M
```

Drop-ins in `/etc/` take precedence over same-or-lower-sorting files in
`/usr/lib/`, and `60-…` sorts after the vendor `40-…`, so `persistent`
wins. `SystemMaxUse` caps disk usage — sensible on SD-card hosts.

**Step 2 — create the persistent directory, apply ACLs, and flush:**

```bash
sudo mkdir -p /var/log/journal
sudo systemd-tmpfiles --create --prefix=/var/log/journal
sudo systemctl restart systemd-journald
sudo journalctl --flush
```

Why this works: the persistent directory is created `2755` and
`systemd-tmpfiles` applies the shipped ACLs, which include a **per-user**
ACL on each `user-<uid>.journal` file — the service user can read exactly
its own user journal and nothing else, and logs survive reboots. Verify as
the service user:

```bash
journalctl --user -n 1 --no-pager   # must print a line, not a permissions error
```

`deploy/scripts/install.sh` warns (without failing) when the journal is
unreadable, pointing here.

To confirm which `Storage=` setting is actually in effect (and which file
set it):

```bash
systemd-analyze cat-config systemd/journald.conf | grep -B2 '^Storage='
```

### Reboot-recovery validation checklist

The reboot test is coordinated with the supervisor (it kills the agent
runtime). After any host reboot, verify — in order:

1. `loginctl show-user openclaw --property=Linger` → `Linger=yes`.
2. `systemctl --user is-active observatory-clickhouse observatory-backend
   observatory-host-collector observatory-agent-collector` → four× `active`
   (allow ~1 min for `Restart=on-failure` to settle ClickHouse before the
   backend's first storage connection).
3. `curl -s http://127.0.0.1:8000/health` → `"status":"ok"` **and**
   `"database":{"connected":true}`.
4. `/monitor` header → expected version + commit (unchanged by the reboot),
   `env Production`, database `connected`.
5. Within ~60 s: fresh heartbeats from `RPSG01` and `A001` (monitor Fleet &
   Services table shows recent `Last heartbeat`; no asset stuck `offline`).
6. `journalctl --user -u observatory-backend -b -n 50` → no errors after the
   startup sequence; `Recent Events` shows a single `service_start`.
7. Host-collector telemetry resumes (monitor Host section `Reported` age
   ≤ telemetry interval) and `Last reboot` reflects the actual reboot time
   in the display timezone (`DISPLAY_TZ`, default host local; offset suffix
   shown, e.g. `Today 20:52 (+08)`).
8. Journal readability (M003.6 §2): `journalctl --user -n 1 --no-pager`
   prints a line (no *insufficient permissions* error) and
   `journalctl --user -b -1 -n 1` shows the previous boot — persistent
   journald survived the reboot (see “Persistent journald” above).

## 13. Frontend Build and Serving (M004 PR3)

The operations console (React SPA, [frontend-architecture.md](frontend-architecture.md))
is served **same-origin by the backend itself** — no new process, port, or
reverse proxy (design §7 of that document; `backend/app/spa.py`).

**Build (on the deploy host or in CI):**

```bash
cd frontend
npm ci          # locked dependencies only (package-lock.json)
npm run build   # tsc -b && vite build → frontend/dist/
```

**Serving flow:**

1. At startup, `create_app()` mounts `frontend/dist` at `/` **only if
   `dist/index.html` exists**. No build → no mount → the backend behaves
   exactly as before (the deploy scripts and test suite need no change).
2. The dist location can be overridden with the `FRONTEND_DIST_DIR`
   environment variable (empty = repository default `frontend/dist`).
3. Route precedence is structural: `/api/*`, `/health`, `/metrics`,
   `/monitor` are registered before the mount and always win. Missing
   assets return hard 404s; unknown `/api/*` paths keep the JSON 404;
   only extension-less navigation paths (e.g. `/fleet/RPSG01`) fall back
   to `index.html`.
4. The SPA inherits the backend's network exposure (loopback/tailnet only,
   SD-003) and its auth model (SD-017: a dedicated `UI01` key entered in
   the Settings screen). `/monitor` remains the zero-JS emergency panel.

**Upgrade note:** rebuilding the frontend does not require a backend
restart for asset changes (files are read per request), but a restart is
needed when the mount must appear on a host that previously had no
`dist/` (the mount decision is made at startup).

---

Related: [architecture.md](architecture.md) · [security.md](security.md) ·
[roadmap.md](roadmap.md) · [requirements.md](requirements.md) ·
[release-process.md](release-process.md)
