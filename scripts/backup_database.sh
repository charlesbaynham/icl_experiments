# Backup the influx database to the Imperial RDS
# and repeat with a timeout

# Backup ARTIQ datasets to the Imperial RDS

export BACKUP_PATH=/mnt/RDS/backups/influxdb
export TIMEOUT=60

echo "Backup loop starting - scanning for results every $TIMEOUT seconds"

while true; do {
influxd backup -portable "$BACKUP_PATH"

echo "Database backup to RDS completed"

sleep $TIMEOUT
}; done
