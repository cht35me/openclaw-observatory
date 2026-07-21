# Observatory Deployment Package (RPSG01 native units)

Production-quality install / upgrade / rollback / uninstall for the
Observatory stack on a single host running systemd user units (Phase 2.1,
Mission M003.5 §2). Strategy and topology: [docs/deployment.md](../docs/deployment.md);
per-release checklists: [docs/release-process.md](../docs/release-process.md).

## Layout

```text
deploy/
├── backend.example.env         # backend config template (placeholders only)
├── systemd/
│   ├── observatory-backend.service
│   └── observatory-clickhouse.service
├── scripts/
│   ├── common.sh               # shared helpers + env-var knobs
│   ├── install.sh              # clean install (idempotent)
│   ├── upgrade.sh <git-ref>    # upgrade to a release tag
│   ├── rollback.sh [git-ref]   # roll back (defaults to recorded previous)
│   └── uninstall.sh [--purge-config]
└── README.md                   # this file
collectors/
├── config.example.env          # collector config template
└── systemd/
    ├── observatory-host-collector.service
    └── observatory-agent-collector.service
```

Four systemd **user** units: `observatory-clickhouse`, `observatory-backend`,
`observatory-host-collector`, `observatory-agent-collector`. Real secrets live
only in `~/.config/observatory/*.env` (mode 600); the repository holds
placeholders (docs/security.md §5).

## Install

```bash
git clone https://github.com/cht35me/openclaw-observatory ~/projects/openclaw-observatory
cd ~/projects/openclaw-observatory
deploy/scripts/install.sh          # venv, config seeds, units, lingering
# edit ~/.config/observatory/{backend,host-collector,agent-collector}.env
#   (generate keys: openssl rand -hex 32; key must be bound to a Fleet ID, SD-017)
deploy/scripts/install.sh --start  # validates config, starts, verifies /health
```

Prerequisites: Python 3.13, `curl`, git; for storage, the native ClickHouse
binary at `~/tools/clickhouse-v80compat/` (ARMv8.0 Pi constraint —
backend/ARCHITECTURE.md §Environments) or a reachable ClickHouse configured in
`backend.env`.

Notes:

- Re-running `install.sh` is safe: existing env files are never overwritten.
- `install.sh` refuses `--start` while any env file still contains a
  `change-me` placeholder.
- Lingering (`loginctl enable-linger`) is enabled so all units start at boot
  without a login session — reboot recovery depends on it.

## Configuration validation (fail fast)

Services validate their environment **before** serving (M003.5 §2):

- Backend: `uvicorn --factory app.main:build_app` calls
  `app.config.load_settings()`, which rejects missing/empty/placeholder
  `API_KEYS`, malformed bindings, bad field types, invalid `LOG_LEVEL`, and
  `OFFLINE_TIMEOUT <= HEARTBEAT_INTERVAL` — one clear, secret-free error on
  stderr, exit code 2, port never bound.
- Collectors: `CollectorConfig.from_env()` rejects missing
  `OBSERVATORY_API_KEY`/`FLEET_ID`, placeholder keys, non-http(s) URLs, and
  non-numeric intervals — clear one-line error, exit code 2.
- The deploy scripts run the same validation out-of-band
  (`validate_all_config` in `common.sh`) so a bad upgrade fails **before** the
  running services are restarted.

## Upgrade

```bash
# set APP_VERSION=<new tag> in ~/.config/observatory/backend.env first (§6)
deploy/scripts/upgrade.sh v0.3.0
```

Records the current commit as the rollback target
(`~/.config/observatory/deploy-state`), fetches + checks out the ref,
reinstalls pinned requirements, validates config, restarts the app units
(never ClickHouse), and verifies `/health`. Then check the `/monitor` header:
version, commit, and environment must match what you intended to deploy.

## Rollback

```bash
deploy/scripts/rollback.sh            # to the recorded previous deployment
deploy/scripts/rollback.sh v0.2.0     # or an explicit ref
```

Restore `APP_VERSION` in `backend.env` to the previous tag. Migrations are
append-only ClickHouse DDL (SD-016/SD-018), so one-step-older releases
tolerate newer schema (docs/deployment.md §8). Report every real rollback and
its cause (release-process.md §5).

## Uninstall

```bash
deploy/scripts/uninstall.sh                 # stop/disable units; config kept
deploy/scripts/uninstall.sh --purge-config  # config moved aside (not deleted)
```

Nothing is ever `rm`ed: unit files and (optionally) the config directory move
to `~/.local/state/observatory-uninstall-<timestamp>/`. ClickHouse data and
the git checkout are never touched.

## Verification (isolated, no production impact)

The scripts take environment overrides so the full lifecycle can be rehearsed
against a scratch clone without touching the live deployment:

```bash
V=~/observatory-verify; git clone <repo> $V/repo
export OBS_REPO=$V/repo OBS_CONFIG_DIR=$V/config OBS_NO_SYSTEMD=1 \
       OBS_HEALTH_URL=http://127.0.0.1:8100/health
$V/repo/deploy/scripts/install.sh          # seeds config; edit it (port 8100,
                                           # CLICKHOUSE_DATABASE=observatory_verify)
# smoke-run: cd $V/repo/backend && .venv/bin/uvicorn --factory app.main:build_app --port 8100
$V/repo/deploy/scripts/upgrade.sh <ref>    # then restart the smoke process
$V/repo/deploy/scripts/rollback.sh         # and again
```

`OBS_NO_SYSTEMD=1` skips unit/lingering/restart steps; everything else
(checkout, pinned deps, config validation, deploy-state bookkeeping) runs
exactly as in production.
