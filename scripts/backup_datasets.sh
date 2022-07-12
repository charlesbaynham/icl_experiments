# Backup ARTIQ datasets to the Imperial RDS

export TIMEOUT=60

echo "Backup loop starting - scanning for results every $TIMEOUT seconds"

while true; do {
rsync \
    --recursive \
    --links \
    --times \
    --quiet \
    --progress \
    --modify-window=2 \
    ./results/ \
    /mnt/RDS/artiq_data/results

rsync \
    --recursive \
    --links \
    --times \
    --quiet \
    --progress \
    --modify-window=2 \
    ./log/ \
    /mnt/RDS/artiq_data/logs

echo "Data synchronized to RDS"

sleep $TIMEOUT
}; done
