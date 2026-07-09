#!/usr/bin/env bash
#
# Keep the live ARTIQ stub catalog in sync with the branches it is built from.
#
# The served catalog is assembled from every ref listed in stubs_sources.yaml
# (see scripts/refresh_stubs.sh / scripts/generate_stubs.py). This watcher polls
# those refs and, whenever any of them advances, rebuilds the catalog and asks
# the running artiq_master to rescan -- so pushing to master, or to any other
# branch feeding the catalog, updates the dashboard with no stack restart.
#
# Each cycle (only while the labserver checkout is on master):
#   1. git fetch --all, so remote-tracking branches are current.
#   2. Fast-forward/merge origin/master into the local master checkout. This may
#      itself rewrite stubs_sources.yaml (add/remove branches), so the branch
#      list is re-read afterwards. A dirty tree or a conflicting merge is left
#      untouched (logged); the merge result is never pushed.
#   3. Re-read stubs_sources.yaml and snapshot the tip of every listed ref. If
#      the set of refs or any tip changed since the last rebuild, run
#      refresh_stubs.sh + artiq_client scan-repository.
#
# On any branch other than master the watcher sits fully idle, so a feature
# branch checked out for live testing is never disturbed. When the checkout
# returns to master, any changes missed while idle are picked up on the next
# cycle.
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

INTERVAL="${WATCH_MASTER_INTERVAL:-15}"
CONNECTION_IP="${ARTIQ_CONNECTION_IP:-::1}"

log() { printf '  [watch_master] %s\n' "$*" >&2; }

# Guard: must be at the repo root (mirrors refresh_stubs.sh and the concurrently
# wrapper). Exiting here is acceptable -- a misconfigured launch should fail loud
# rather than silently never syncing.
[[ -f .aion_artiq_root ]] || {
    log "must be run from the repository root (missing .aion_artiq_root)"
    exit 1
}

# Fast-forward/merge origin/master into the local master checkout, when safe.
# Assumes HEAD is already on master. Never pushes; logs and leaves master
# untouched on a dirty tree or a conflicting merge.
update_master_from_origin() {
    local local_sha remote_sha
    local_sha="$(git rev-parse HEAD 2>/dev/null)" || return 0
    remote_sha="$(git rev-parse origin/master 2>/dev/null)" || return 0
    [[ "$local_sha" == "$remote_sha" ]] && return 0             # up to date
    git merge-base --is-ancestor "$remote_sha" HEAD && return 0 # local ahead only

    if [[ -n "$(git status --porcelain)" ]]; then
        log "uncommitted local changes on master; skipping fast-forward/merge"
        return 0
    fi

    log "new commits on origin/master; integrating by merge"
    if git merge --no-edit origin/master >/dev/null 2>&1; then
        log "master updated to $(git rev-parse --short HEAD)"
    else
        log "automatic merge failed (conflicts); aborting, leaving master untouched"
        git merge --abort 2>/dev/null || true
    fi
}

# Print "<ref> <sha>" for every branch in stubs_sources.yaml, sorted. Unresolved
# refs record MISSING so they still register as changed if they later appear.
branch_snapshot() {
    local branches ref sha
    branches="$(python3 scripts/stub_branches.py)" || return 1
    while IFS= read -r ref; do
        [[ -n "$ref" ]] || continue
        sha="$(git rev-parse --verify -q "${ref}^{commit}" 2>/dev/null || echo MISSING)"
        printf '%s %s\n' "$ref" "$sha"
    done <<<"$branches" | sort
}

refresh_and_rescan() {
    if ! ./scripts/refresh_stubs.sh >/dev/null; then
        log "refresh_stubs failed; will retry next cycle"
        return 1
    fi
    log "triggering repository rescan on ${CONNECTION_IP}"
    artiq_client -s "$CONNECTION_IP" scan-repository \
        || log "scan-repository failed (master not up yet?); catalog will lag until next change"
}

last_snapshot=""
log "watching stub-source branches every ${INTERVAL}s"
while true; do
    sleep "$INTERVAL"

    # Idle entirely unless the checkout is on master.
    [[ "$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" == "master" ]] || continue

    # Update all remote-tracking branches before deciding anything.
    git fetch --all --quiet 2>/dev/null \
        || { log "git fetch --all failed; retrying next cycle"; continue; }

    # Bring local master up to date first: this can rewrite stubs_sources.yaml.
    update_master_from_origin

    # Re-read the (possibly just-updated) branch list and snapshot every tip.
    snapshot="$(branch_snapshot)" \
        || { log "could not read stubs_sources.yaml; retrying next cycle"; continue; }
    [[ "$snapshot" == "$last_snapshot" ]] && continue

    # Report which refs moved (all of them on the first rebuild).
    changed=""
    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        grep -qxF -- "$line" <<<"$last_snapshot" || changed+="${changed:+, }${line%% *}"
    done <<<"$snapshot"
    log "stub-source branch(es) changed: ${changed:-<all>}; rebuilding catalog"

    refresh_and_rescan && last_snapshot="$snapshot"
done
