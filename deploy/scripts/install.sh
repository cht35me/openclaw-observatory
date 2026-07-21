#!/usr/bin/env bash
# Observatory clean install (RPSG01 native systemd user units; M003.5 §2).
#
# Usage:
#   deploy/scripts/install.sh [--start]
#
# Idempotent: safe to re-run. Never overwrites existing env files, never
# touches ClickHouse data. With --start the services are (re)started and the
# backend health endpoint is verified; without it the script stops after
# enabling units so you can edit the seeded config first.
#
# Environment overrides: see deploy/scripts/common.sh header.

set -euo pipefail
. "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

START=0
for arg in "$@"; do
  case "$arg" in
    --start) START=1 ;;
    *) die "unknown argument: $arg (usage: install.sh [--start])" ;;
  esac
done

require_repo
command -v curl >/dev/null || die "curl is required"
command -v "$OBS_PYTHON" >/dev/null || die "$OBS_PYTHON is required"

log "installing from $OBS_REPO (commit $(current_commit))"

# 1. Python dependencies (pinned; docs/security.md §8).
install_python_deps

# 2. Configuration: seed from the committed examples, NEVER overwrite.
#    Real values are edited in by the operator; placeholders are rejected by
#    startup validation (app/config.py, observatory_collectors/config.py).
mkdir -p "$OBS_CONFIG_DIR"
seed_config() {
  local target="$OBS_CONFIG_DIR/$1" source="$OBS_REPO/$2"
  if [ -f "$target" ]; then
    log "keeping existing $target"
  else
    install -m 600 "$source" "$target"
    log "seeded $target from $2 — EDIT THE PLACEHOLDERS before starting"
  fi
}
seed_config backend.env deploy/backend.example.env
seed_config host-collector.env collectors/config.example.env
seed_config agent-collector.env collectors/config.example.env

# 3. systemd user units + lingering (automatic startup after reboot).
if systemd_enabled; then
  mkdir -p "$OBS_UNIT_DIR"
  install -m 644 "$OBS_REPO/deploy/systemd/observatory-backend.service" "$OBS_UNIT_DIR/"
  install -m 644 "$OBS_REPO/collectors/systemd/observatory-host-collector.service" "$OBS_UNIT_DIR/"
  install -m 644 "$OBS_REPO/collectors/systemd/observatory-agent-collector.service" "$OBS_UNIT_DIR/"
  if [ -x "$OBS_CLICKHOUSE_DIR/clickhouse" ]; then
    install -m 644 "$OBS_REPO/deploy/systemd/observatory-clickhouse.service" "$OBS_UNIT_DIR/"
    UNITS=("$OBS_CLICKHOUSE_UNIT" "${OBS_APP_UNITS[@]}")
  else
    warn "no ClickHouse binary at $OBS_CLICKHOUSE_DIR — skipping its unit" \
         "(backend/ARCHITECTURE.md §Environments explains the native-binary setup)"
    UNITS=("${OBS_APP_UNITS[@]}")
  fi
  systemctl --user daemon-reload
  systemctl --user enable "${UNITS[@]}"
  log "enabled units: ${UNITS[*]}"

  # Lingering keeps user units running without a login session and starts
  # them at boot — required for reboot recovery (docs/deployment.md §12).
  if [ "$(loginctl show-user "$USER" --property=Linger --value 2>/dev/null)" != "yes" ]; then
    log "enabling systemd lingering for $USER"
    loginctl enable-linger "$USER"
  else
    log "lingering already enabled for $USER"
  fi
else
  log "OBS_NO_SYSTEMD=1 — skipping unit installation and lingering"
fi

# 4. Journal readability check (M003.6 §2) — WARN only, never fail: on a
#    volatile-journal host (Storage=auto without /var/log/journal/<id>) the
#    service user cannot read even its own user journal, which cripples
#    post-incident forensics. The fix is a one-time sudo host op.
if systemd_enabled && ! journalctl --user -n 1 --no-pager >/dev/null 2>&1; then
  warn "journalctl --user is not readable for $USER — service logs are"
  warn "invisible and lost on reboot. Enable persistent journald (one-time,"
  warn "needs sudo — docs/deployment.md §12 'Persistent journald'):"
  warn "  sudo mkdir -p /var/log/journal"
  warn "  sudo systemd-tmpfiles --create --prefix=/var/log/journal"
  warn "  sudo journalctl --flush"
fi

# 5. Fail-fast config validation — the same checks the services run at start.
if grep -q change-me "$OBS_CONFIG_DIR"/backend.env "$OBS_CONFIG_DIR"/host-collector.env \
     "$OBS_CONFIG_DIR"/agent-collector.env 2>/dev/null; then
  warn "config files under $OBS_CONFIG_DIR still contain placeholders."
  warn "Edit them (generate keys: openssl rand -hex 32), then run:"
  warn "  deploy/scripts/install.sh --start"
  [ "$START" = 1 ] && die "refusing --start with placeholder configuration"
  exit 0
fi
validate_all_config

# 6. Optional start + health verification.
if [ "$START" = 1 ]; then
  if systemd_enabled; then
    [ -x "$OBS_CLICKHOUSE_DIR/clickhouse" ] && systemctl --user start "$OBS_CLICKHOUSE_UNIT"
    systemctl --user restart "${OBS_APP_UNITS[@]}"
    wait_healthy 90
  else
    log "OBS_NO_SYSTEMD=1 — start the backend manually, e.g.:"
    log "  cd $OBS_REPO/backend && .venv/bin/uvicorn --factory app.main:build_app --host 127.0.0.1 --port 8000"
  fi
fi

record_deploy_state "none" "$(current_commit)" install
log "install complete"
