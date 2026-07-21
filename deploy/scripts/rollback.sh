#!/usr/bin/env bash
# Observatory rollback to the previous deployment (release-process.md §5).
#
# Usage:
#   deploy/scripts/rollback.sh [git-ref]
#
# With no argument the target is `previous_ref` recorded by upgrade.sh in
# ~/.config/observatory/deploy-state. Migrations are append-only ClickHouse
# DDL (SD-016), so the older release tolerates schema created by the newer
# one — rollback is checkout + deps + restart, no data surgery.
#
# Remember to restore APP_VERSION in backend.env to the previous tag
# (release-process.md §5) — the monitor header should tell the truth.

set -euo pipefail
. "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

TARGET="${1:-}"
if [ -z "$TARGET" ]; then
  [ -f "$OBS_STATE_FILE" ] || die "no deploy state at $OBS_STATE_FILE — pass an explicit git ref"
  TARGET="$(sed -n 's/^previous_ref=//p' "$OBS_STATE_FILE")"
  [ -n "$TARGET" ] && [ "$TARGET" != none ] || die "deploy state has no previous_ref — pass an explicit git ref"
fi

require_repo
require_clean_tree

CURRENT="$(current_commit)"
log "rolling back: $CURRENT -> $TARGET"
COMMIT=$(git -C "$OBS_REPO" rev-parse --verify --quiet "$TARGET^{commit}") \
  || die "unknown git ref: $TARGET"
git -C "$OBS_REPO" checkout --quiet --detach "$COMMIT"

# Requirements may differ between releases; reinstall the pinned set.
install_python_deps
validate_all_config

record_deploy_state "$CURRENT" "$(current_commit)" rollback
restart_app_units

if systemd_enabled; then
  if wait_healthy 90; then
    log "rollback to $TARGET complete — verify the /monitor header and report the cause (release-process.md §5)"
  else
    warn "health verification FAILED after rollback — inspect: journalctl --user -u observatory-backend -n 50"
    exit 1
  fi
else
  log "rollback to $TARGET staged (OBS_NO_SYSTEMD=1) — restart your process, then verify $OBS_HEALTH_URL"
fi
