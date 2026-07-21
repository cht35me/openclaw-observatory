#!/usr/bin/env bash
# Observatory uninstall (M003.5 §2). Conservative by design:
#
#   default        stop + disable units, remove unit files (backed up first)
#   --purge-config additionally moves ~/.config/observatory aside (never rm)
#
# NEVER touched: the ClickHouse data directory (~/tools/clickhouse-v80compat)
# and the git checkout. Removing telemetry history is a deliberate manual act,
# not a script side effect.

set -euo pipefail
. "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

PURGE=0
for arg in "$@"; do
  case "$arg" in
    --purge-config) PURGE=1 ;;
    *) die "unknown argument: $arg (usage: uninstall.sh [--purge-config])" ;;
  esac
done

BACKUP_DIR="$HOME/.local/state/observatory-uninstall-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

ALL_UNITS=("${OBS_APP_UNITS[@]}" "$OBS_CLICKHOUSE_UNIT")

if systemd_enabled; then
  for unit in "${ALL_UNITS[@]}"; do
    systemctl --user stop "$unit" 2>/dev/null || true
    systemctl --user disable "$unit" 2>/dev/null || true
  done
  log "stopped and disabled: ${ALL_UNITS[*]}"
  for unit in "${ALL_UNITS[@]}"; do
    if [ -f "$OBS_UNIT_DIR/$unit.service" ]; then
      mv "$OBS_UNIT_DIR/$unit.service" "$BACKUP_DIR/"
    fi
  done
  systemctl --user daemon-reload
  log "unit files moved to $BACKUP_DIR"
else
  log "OBS_NO_SYSTEMD=1 — no units to remove"
fi

if [ "$PURGE" = 1 ] && [ -d "$OBS_CONFIG_DIR" ]; then
  mv "$OBS_CONFIG_DIR" "$BACKUP_DIR/observatory-config"
  log "config moved to $BACKUP_DIR/observatory-config (contains secrets — delete deliberately)"
else
  log "config preserved at $OBS_CONFIG_DIR (use --purge-config to move it aside)"
fi

log "NOT touched: ClickHouse data ($OBS_CLICKHOUSE_DIR), git checkout ($OBS_REPO)"
log "uninstall complete; backups in $BACKUP_DIR"
