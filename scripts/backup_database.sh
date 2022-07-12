# Backup the influx database to the Imperial RDS
# ==============================================
# This script backs up the influx database at midnight every night

export BACKUP_PATH=/mnt/RDS/backups/influxdb

echo "Database backup monitor started - will backup at midnight nightly"

while true; do {
    # Wait until midnight
    sleep $(( $(date -f - +%s- <<< "tomorrow 00:00"$'\nnow') 0 ))

    export DIRNAME=`date +"%Y%m%d-%H%M%S"`
    mkdir "$BACKUP_PATH/$DIRNAME"
    influxd backup -portable "$BACKUP_PATH/$DIRNAME"

    echo "Database backup to RDS completed at DIRNAME=${DIRNAME}"
}; done
