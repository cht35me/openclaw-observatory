#!/usr/bin/env bash
# Observatory upgrade to a release tag or ref (docs/release-process.md §4).
#
# Usage:
#   deploy/scripts/upgrade.sh <git-ref>        # e.g. v0.3.0
#
# Steps: record rollback target → fetch + checkout → pinned deps → validate
# config → restart app units → verify health. ClickHouse is never restarted
# by an application upgrade. On failure, roll back with:
#   deploy/scripts/rollback.sh
#
# Remember to set APP_VERSION in ~/.config/observatory/backend.env to the new
# tag BEFORE upgrading a tagged release (release-process.md §6) — the script
# warns when they disagree.

set -euo pipefail
. "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

TARGET="${1:-}"
[ -n "$TARGET" ] || die "usage: upgrade.sh <git-ref> (release tag, branch, or commit)"

require_repo
require_clean_tree

PREVIOUS="$(current_commit)"
log "current deployment: $PREVIOUS (rollback target)"

if git -C "$OBS_REPO" remote get-url origin >/dev/null 2>&1; then
  log "fetching origin (with tags)"
  git -C "$OBS_REPO" fetch --tags origin
fi
# Resolve remote-first so a branch name means its *fetched* head, not a
# stale local branch left over from clone time; deploy detached, matching
# how release tags are deployed.
if COMMIT=$(git -C "$OBS_REPO" rev-parse --verify --quiet "origin/$TARGET^{commit}"); then
  :
elif COMMIT=$(git -C "$OBS_REPO" rev-parse --verify --quiet "$TARGET^{commit}"); then
  :
else
  die "unknown git ref: $TARGET"
fi
log "checking out $TARGET ($COMMIT)"
git -C "$OBS_REPO" checkout --quiet --detach "$COMMIT"

install_python_deps

# Fail fast BEFORE restarting anything: if the new release rejects the current
# configuration, the running (old) services stay up untouched.
validate_all_config

# Version bookkeeping sanity (release-process.md §6): the deployed
# APP_VERSION should equal the tag being deployed.
if [[ "$TARGET" == v* ]] && ! grep -q "^APP_VERSION=$TARGET$" "$OBS_CONFIG_DIR/backend.env"; then
  warn "APP_VERSION in $OBS_CONFIG_DIR/backend.env does not equal $TARGET — update it (monitor header will disagree with the tag)"
fi

record_deploy_state "$PREVIOUS" "$(current_commit)" upgrade
restart_app_units

if systemd_enabled; then
  if wait_healthy 90; then
    log "upgrade to $TARGET complete — check the /monitor header (version + commit)"
  else
    warn "health verification FAILED — inspect: journalctl --user -u observatory-backend -n 50"
    warn "roll back with: deploy/scripts/rollback.sh"
    exit 1
  fi
else
  log "upgrade to $TARGET staged (OBS_NO_SYSTEMD=1) — restart your process, then verify $OBS_HEALTH_URL"
fi
