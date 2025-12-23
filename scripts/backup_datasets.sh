# Backup ARTIQ datasets to the Imperial RDS

# Imperial account with access to the AION RDS
SSH_USER=stronlab
# This file must contain the ssh password for the rds user account
SSH_PASSWORD_FILE=~/.sshpassword
SSH_RDS_HOST=dtn-c.cx3.hpc.ic.ac.uk  # This is the RDS data transfer node
RDS_RESULTS_PATH=/rds/general/project/ultracoldsr-aion/live/artiq_data/results
RDS_LOGS_PATH=/rds/general/project/ultracoldsr-aion/live/artiq_data/logs

# Check that password file exists
if [ ! -f $SSH_PASSWORD_FILE ]; then
    echo "SSH password file $SSH_PASSWORD_FILE not found!"
    exit 1
fi

TIMEOUT=60

echo "Backup loop starting - scanning for results every $TIMEOUT seconds"

while true; do {
    echo Starting backup at $(date)

    if sshpass -f "${SSH_PASSWORD_FILE}" \
        rsync \
            --recursive \
            --links \
            --progress \
            --modify-window=2 \
            ./results/ \
            ${SSH_USER}@${SSH_RDS_HOST}:${RDS_RESULTS_PATH}; then

        echo Pinging cronitor
        curl https://cronitor.link/p/5de5a2d2d5b64e9b8711a630ca78dfcc/XMCp2l
    else
        echo Rsync failed
    fi

    sshpass -f "${SSH_PASSWORD_FILE}" rsync \
        --recursive \
        --links \
        --quiet \
        --progress \
        --modify-window=2 \
        ./log/ \
        ${SSH_USER}@${SSH_RDS_HOST}:${RDS_LOGS_PATH}

    echo "Data synchronized to RDS"

    sleep $TIMEOUT
}; done
