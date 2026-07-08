#!/usr/bin/env bash
#
# Keep the live ARTIQ stub catalog in sync with origin/master.
#
# Poll origin for new master commits; when the labserver checkout is on a clean
# master, fast-forward/merge them in, rebuild the stub catalog (refresh_stubs.sh)
# and ask the running artiq_master to rescan its repository. The catalog then
# reflects the new stubs_sources.yaml with no stack restart.
#
# Behaviour (see the "Auto-update the live stub catalog" design):
#   * Only acts on the master branch. On any other branch it sits idle, so a
#     feature branch checked out for live testing is never disturbed.
#   * Refuses to touch a dirty tree: uncommitted local changes -> skip + log.
#   * Integrates by merge. Fast-forward is the common case; if local master has
#     its own commits it attempts an automatic merge, and on conflict aborts the
#     merge (leaving master untouched) and logs. The result is never pushed.
#
# Never exits: it is launched inside the `concurrently` stack, whose
# --kill-others would tear the whole stack down if any command returned. Run
# from the repo root (the dir holding .aion_artiq_root). Config via env:
#   WATCH_MASTER_INTERVAL  poll period in seconds (default 60)
#   ARTIQ_CONNECTION_IP    server the master listens on (default ::1)
#
# NB: `set -e` is deliberately omitted -- a transient git error must never kill
# the loop and collapse the stack.
set -uo pipefail

INTERVAL="${WATCH_MASTER_INTERVAL:-60}"
CONNECTION_IP="${ARTIQ_CONNECTION_IP:-::1}"

log() { printf '  [watch_master] %s\n' "$*" >&2; }

# Guard: must be at the repo root (mirrors refresh_stubs.sh and the concurrently
# wrapper). Exiting here is acceptable -- a misconfigured launch should fail loud
# rather than silently never syncing.
[[ -f .aion_artiq_root ]] || {
    log "must be run from the repository root (missing .aion_artiq_root)"
    exit 1
}

refresh_and_rescan() {
    log "master advanced to $(git rev-parse --short HEAD); rebuilding stub catalog"
    if ! ./scripts/refresh_stubs.sh >/dev/null; then
        log "refresh_stubs failed; will retry next cycle"
        return 1
    fi
    log "triggering repository rescan on ${CONNECTION_IP}"
    artiq_client -s "$CONNECTION_IP" scan-repository \
        || log "scan-repository failed (master not up yet?); catalog will lag until next change"
}

log "watching origin/master every ${INTERVAL}s"
while true; do
    sleep "$INTERVAL"

    # Only act on master; idle on any feature branch.
    [[ "$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" == "master" ]] || continue

    git fetch --quiet origin master 2>/dev/null \
        || { log "fetch failed; retrying next cycle"; continue; }

    local_sha="$(git rev-parse HEAD 2>/dev/null)" || continue
    remote_sha="$(git rev-parse origin/master 2>/dev/null)" || continue
    [[ "$local_sha" == "$remote_sha" ]] && continue             # up to date
    git merge-base --is-ancestor "$remote_sha" HEAD && continue # local ahead only

    # Refuse to touch a dirty tree.
    if [[ -n "$(git status --porcelain)" ]]; then
        log "uncommitted local changes on master; skipping auto-update"
        continue
    fi

    log "new commits on origin/master; integrating by merge"
    if git merge --no-edit origin/master >/dev/null 2>&1; then
        refresh_and_rescan
    else
        log "automatic merge failed (conflicts); aborting, leaving master untouched"
        git merge --abort 2>/dev/null || true
    fi
done
