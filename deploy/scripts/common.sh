# shellcheck shell=bash
# Shared helpers for the Observatory deployment scripts (M003.5 §2).
# Sourced by install.sh / upgrade.sh / rollback.sh / uninstall.sh — not run.
#
# Every knob is an environment variable with a production default, so the
# same scripts drive the real RPSG01 deployment AND isolated verification
# installs (see deploy/README.md §Verification):
#
#   OBS_REPO        deployment checkout (default: repo containing this script)
#   OBS_CONFIG_DIR  env files + deploy state   (default ~/.config/observatory)
#   OBS_UNIT_DIR    systemd user units         (default ~/.config/systemd/user)
#   OBS_HEALTH_URL  backend health endpoint    (default http://127.0.0.1:8000/health)
#   OBS_NO_SYSTEMD  =1 skips all systemctl/loginctl steps (isolated verify, CI)
#   OBS_PYTHON      interpreter for venv + collectors (default python3)

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OBS_REPO="${OBS_REPO:-$(cd -- "$SCRIPT_DIR/../.." && pwd)}"
OBS_CONFIG_DIR="${OBS_CONFIG_DIR:-$HOME/.config/observatory}"
OBS_UNIT_DIR="${OBS_UNIT_DIR:-$HOME/.config/systemd/user}"
OBS_HEALTH_URL="${OBS_HEALTH_URL:-http://127.0.0.1:8000/health}"
OBS_NO_SYSTEMD="${OBS_NO_SYSTEMD:-0}"
OBS_PYTHON="${OBS_PYTHON:-python3}"
OBS_VENV="$OBS_REPO/backend/.venv"
OBS_STATE_FILE="$OBS_CONFIG_DIR/deploy-state"

# Units managed by these scripts. ClickHouse is listed last and treated
# specially: its unit is only installed when the native binary exists, and
# upgrade/rollback never restart it (application releases do not change it).
OBS_APP_UNITS=(observatory-backend observatory-host-collector observatory-agent-collector)
OBS_CLICKHOUSE_UNIT=observatory-clickhouse
OBS_CLICKHOUSE_DIR="${OBS_CLICKHOUSE_DIR:-$HOME/tools/clickhouse-v80compat}"

log()  { printf '[deploy] %s\n' "$*"; }
warn() { printf '[deploy] WARNING: %s\n' "$*" >&2; }
die()  { printf '[deploy] ERROR: %s\n' "$*" >&2; exit 1; }

require_repo() {
  [ -d "$OBS_REPO/.git" ] || die "OBS_REPO is not a git checkout: $OBS_REPO"
  [ -f "$OBS_REPO/backend/requirements.txt" ] || die "not an Observatory checkout: $OBS_REPO"
}

require_clean_tree() {
  if [ "${OBS_ALLOW_DIRTY:-0}" = 1 ]; then return 0; fi
  if ! git -C "$OBS_REPO" diff --quiet HEAD -- 2>/dev/null; then
    die "working tree at $OBS_REPO has uncommitted changes (set OBS_ALLOW_DIRTY=1 to override)"
  fi
}

current_commit() { git -C "$OBS_REPO" rev-parse HEAD; }

systemd_enabled() { [ "$OBS_NO_SYSTEMD" != 1 ]; }

install_python_deps() {
  if [ ! -x "$OBS_VENV/bin/python" ]; then
    log "creating virtualenv at $OBS_VENV"
    "$OBS_PYTHON" -m venv "$OBS_VENV"
  fi
  log "installing pinned backend requirements"
  "$OBS_VENV/bin/pip" install --quiet -r "$OBS_REPO/backend/requirements.txt"
}

# --- configuration validation (fail fast BEFORE any restart, M003.5 §2) ----

validate_backend_config() {
  local env_file="$OBS_CONFIG_DIR/backend.env"
  [ -f "$env_file" ] || die "missing $env_file (run install.sh first)"
  # Subshell: export the env file exactly as systemd EnvironmentFile= would,
  # then run the same load_settings() the server factory runs at startup.
  if (set -a; . "$env_file"; set +a; cd "$OBS_REPO/backend" && \
      "$OBS_VENV/bin/python" -c 'from app.config import load_settings; load_settings()'); then
    log "backend configuration OK ($env_file)"
  else
    die "backend configuration INVALID ($env_file) — fix it before starting the service"
  fi
}

validate_collector_config() {
  local name="$1" env_file="$OBS_CONFIG_DIR/$1.env"
  [ -f "$env_file" ] || die "missing $env_file (run install.sh first)"
  if (set -a; . "$env_file"; set +a; cd "$OBS_REPO/collectors" && \
      "$OBS_PYTHON" -c 'from observatory_collectors.config import CollectorConfig; CollectorConfig.from_env()'); then
    log "collector configuration OK ($env_file)"
  else
    die "collector configuration INVALID ($env_file) — fix it before starting the service"
  fi
}

validate_all_config() {
  validate_backend_config
  validate_collector_config host-collector
  validate_collector_config agent-collector
}

# --- health verification -----------------------------------------------------

wait_healthy() {
  local timeout="${1:-60}" waited=0 body
  log "waiting for $OBS_HEALTH_URL (timeout ${timeout}s)"
  while [ "$waited" -lt "$timeout" ]; do
    if body=$(curl -fsS --max-time 3 "$OBS_HEALTH_URL" 2>/dev/null); then
      if printf '%s' "$body" | grep -q '"status":"ok"'; then
        log "health OK: $body"
        printf '%s' "$body" | grep -q '"connected":true' \
          || warn "backend is up but the database is not connected (degraded)"
        return 0
      fi
    fi
    sleep 2; waited=$((waited + 2))
  done
  warn "backend did not become healthy within ${timeout}s"
  return 1
}

restart_app_units() {
  systemd_enabled || { log "OBS_NO_SYSTEMD=1 — skipping unit restart (restart your process manually)"; return 0; }
  log "restarting: ${OBS_APP_UNITS[*]}"
  systemctl --user daemon-reload
  systemctl --user restart "${OBS_APP_UNITS[@]}"
}

record_deploy_state() {
  # Rollback bookkeeping (docs/release-process.md §5): remember where we came
  # from so rollback.sh works with no arguments.
  local previous="$1" current="$2" action="${3:-deploy}"
  mkdir -p "$OBS_CONFIG_DIR"
  {
    printf 'previous_ref=%s\n' "$previous"
    printf 'current_ref=%s\n' "$current"
    printf 'action=%s\n' "$action"
    printf 'timestamp=%s\n' "$(date -Is)"
  } > "$OBS_STATE_FILE"
  chmod 600 "$OBS_STATE_FILE"
  log "deploy state recorded: $previous -> $current ($action)"
}
