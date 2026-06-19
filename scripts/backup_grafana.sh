# Backup the Grafana instance to the Imperial RDS
# ===============================================
# Grafana's entire state (dashboards, datasources, users, alert rules,
# settings) lives in a single SQLite database, grafana.db. This script takes a
# consistent online snapshot of it - plus the small alerting state dir - every
# night at midnight, then mirrors the backups to the RDS.
#
# Backups are built and rotated on local disk first, then pushed to the RDS
# with rsync over ssh (the same robust transport backup_datasets.sh uses).
# We deliberately do NOT write directly to the /mnt/RDS CIFS mount: that mount
# is flaky and has bitten us before.
#
# Reinstallable/transient state is deliberately NOT backed up:
#   - plugins/ : reinstalled by Grafana on startup
#   - logs/    : transient
#   - provisioning : reproduced from the nix flake (GF_PATHS_PROVISIONING)
#
# Rotation (grandfather-father-son) keeps, at most:
#   - the latest backup from each of the last 3 days
#   - the latest backup from each of the last 3 weeks
#   - the latest backup from each of the last 12 months
# A single backup can satisfy several tiers, so the kept set is their union.
# Rotation happens on the local store; rsync --delete propagates it to the RDS.

# Imperial account with access to the AION RDS (matches backup_datasets.sh)
SSH_USER=stronlab
# This file must contain the ssh password for the rds user account
SSH_PASSWORD_FILE=~/.sshpassword
SSH_RDS_HOST=dtn-c.cx3.hpc.ic.ac.uk  # This is the RDS data transfer node
RDS_BACKUP_PATH=/rds/general/project/ultracoldsr-aion/live/backups/grafana

# Local canonical backup store (fast, reliable local disk). Rotation happens
# here, then the whole directory is mirrored to the RDS.
LOCAL_BACKUP_DIR=${GRAFANA_BACKUP_DIR:-$HOME/backups/grafana}

# Grafana stores its data here (matches GF_PATHS_DATA in the grafana app).
GRAFANA_DATA_DIR=${GF_PATHS_DATA:-$HOME/.grafana/data}

KEEP_DAYS=3
KEEP_WEEKS=3
KEEP_MONTHS=12

# Take a consistent, integrity-checked archive of the live Grafana state into
# the local backup store. Safe to run while Grafana is serving: sqlite's online
# .backup handles the WAL, and we open the DB read-only so we never touch the
# live file.
backup_grafana() {
    local ts archive stage
    ts=$(date +"%Y%m%d-%H%M%S")
    archive="$LOCAL_BACKUP_DIR/grafana-$ts.tar.gz"
    stage=$(mktemp -d -t grafana_backup_XXXXXX)

    sqlite3 "file:$GRAFANA_DATA_DIR/grafana.db?mode=ro" ".backup '$stage/grafana.db'"

    local check
    check=$(sqlite3 "$stage/grafana.db" "PRAGMA integrity_check;")
    if [ "$check" != "ok" ]; then
        echo "Grafana backup ABORTED: snapshot failed integrity_check: $check"
        rm -rf "$stage"
        return 1
    fi

    # Small extra state. csv/png are render scratch dirs - include if present.
    cp -a "$GRAFANA_DATA_DIR/alerting" "$stage/alerting" 2>/dev/null || true
    cp -a "$GRAFANA_DATA_DIR/csv" "$stage/csv" 2>/dev/null || true
    cp -a "$GRAFANA_DATA_DIR/png" "$stage/png" 2>/dev/null || true

    mkdir -p "$LOCAL_BACKUP_DIR"
    tar -czf "$archive" -C "$stage" .
    rm -rf "$stage"

    if gzip -t "$archive"; then
        echo "Grafana backup written to $archive ($(du -h "$archive" | cut -f1))"
    else
        echo "Grafana backup FAILED: archive is corrupt: $archive"
        rm -f "$archive"
        return 1
    fi
}

# Grandfather-father-son rotation of the local store. Walk backups newest-first;
# a backup is kept if it is the newest one in one of the last $KEEP_DAYS days,
# $KEEP_WEEKS ISO weeks, or $KEEP_MONTHS months. Everything else is deleted.
prune_grafana() {
    local -A seen_day seen_week seen_month keep
    local n_day=0 n_week=0 n_month=0
    local f base stamp ymd iso daykey weekkey monthkey

    for f in $(ls -1 "$LOCAL_BACKUP_DIR"/grafana-*.tar.gz 2>/dev/null | sort -r); do
        base=$(basename "$f")
        stamp=${base#grafana-}      # YYYYMMDD-HHMMSS.tar.gz
        stamp=${stamp%.tar.gz}      # YYYYMMDD-HHMMSS
        ymd=${stamp%-*}             # YYYYMMDD
        iso="${ymd:0:4}-${ymd:4:2}-${ymd:6:2}"
        daykey=$ymd
        weekkey=$(date -d "$iso" +%G-W%V)   # ISO year + week, e.g. 2026-W25
        monthkey=${ymd:0:6}                 # YYYYMM

        if [ -z "${seen_day[$daykey]:-}" ] && [ "$n_day" -lt "$KEEP_DAYS" ]; then
            seen_day[$daykey]=1; n_day=$((n_day + 1)); keep[$f]=1
        fi
        if [ -z "${seen_week[$weekkey]:-}" ] && [ "$n_week" -lt "$KEEP_WEEKS" ]; then
            seen_week[$weekkey]=1; n_week=$((n_week + 1)); keep[$f]=1
        fi
        if [ -z "${seen_month[$monthkey]:-}" ] && [ "$n_month" -lt "$KEEP_MONTHS" ]; then
            seen_month[$monthkey]=1; n_month=$((n_month + 1)); keep[$f]=1
        fi
    done

    for f in $(ls -1 "$LOCAL_BACKUP_DIR"/grafana-*.tar.gz 2>/dev/null); do
        if [ -z "${keep[$f]:-}" ]; then
            echo "Pruning old backup $(basename "$f")"
            rm -f "$f"
        fi
    done
}

# Mirror the local backup store to the RDS over ssh. --delete makes the remote
# match local exactly, so local rotation (prune_grafana) is propagated.
sync_to_rds() {
    if [ ! -f "$SSH_PASSWORD_FILE" ]; then
        echo "SSH password file $SSH_PASSWORD_FILE not found - skipping RDS sync!"
        return 1
    fi

    # rsync won't create intermediate remote dirs; ensure the target exists.
    sshpass -f "$SSH_PASSWORD_FILE" \
        ssh "${SSH_USER}@${SSH_RDS_HOST}" "mkdir -p '${RDS_BACKUP_PATH}'" || return 1


    sshpass -f "$SSH_PASSWORD_FILE" \
        rsync \
            --recursive \
            --times \
            --delete \
            --modify-window=2 \
            "$LOCAL_BACKUP_DIR/" \
            "${SSH_USER}@${SSH_RDS_HOST}:${RDS_BACKUP_PATH}/"
}

echo "Grafana backup monitor started - will backup at midnight nightly"

while true; do {
   # Wait until midnight
   sleep $(( $(date -f - +%s- <<< "tomorrow 00:00"$'\nnow') 0 ))

   if backup_grafana; then
       prune_grafana
       if sync_to_rds; then
           echo "Grafana backup mirrored to RDS at $(date +"%Y%m%d-%H%M%S")"
       else
           echo "Grafana backup saved locally but RDS sync failed at $(date +"%Y%m%d-%H%M%S")"
       fi
   fi
}; done
