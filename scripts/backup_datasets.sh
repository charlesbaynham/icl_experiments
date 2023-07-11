# Backup ARTIQ datasets to the Imperial RDS

export TIMEOUT=60

echo "Backup loop starting - scanning for results every $TIMEOUT seconds"

while true; do {
    if rsync \
            --recursive \
            --links \
            --times \
            --quiet \
            --progress \
            --modify-window=2 \
            ./results/ \
            /mnt/RDS/artiq_data/results ; then
        echo Pinging cronitor
        curl https://cronitor.link/p/5de5a2d2d5b64e9b8711a630ca78dfcc/XMCp2l
    else
        echo Rsync failed
    fi

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
