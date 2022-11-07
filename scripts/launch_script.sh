
############################################################
# Help                                                     #
############################################################

read -r -d '' HELP_TEXT << EOM
This is a launch script for ARTIQ, to start:
  * artiq_master
  * artiq_ctlmgr
  * (optional) artiq_dashboard

If any of these programmes close (e.g. if you close the dashboard), ALL will
be shut down.

Do not run this script directly! If you do, you are responsible for making
sure that it is run in the correct environment and that that environment is
reproducable. Instead, allow nix to handle the details by launching this
script with

    nix run .#run_artiq

Arguments:

--gui   - Also start artiq_dashboard. Note that closing the dashboard will
          also shut down the master. Use "nix run .#run_dashboard" instead to
          connect a dashboard to an already-running master.

--dev   - Run in non-git mode instead of git mode. Useful for local
          debugging, but prevents version stamping of results so don't use
          this for producing data that you care about!

--help  - Display this help text
EOM

Help()
{
   # Display Help
   echo "$HELP_TEXT"
   exit 0
}

echo WARNING: Performing nasty SSL certificate hack
export SSL_CERT_DIR=/etc/ssl/certs

############################################################
# Process the input options. Add options as needed.        #
############################################################

# NOTE: This requires GNU getopt.  On Mac OS X and FreeBSD, you have to install this
# separately; see below.
TEMP=$(getopt -o hdg --long help,dev,gui \
              -n 'launch_script' -- "$@")

if [ $? != 0 ] ; then echo "Terminating..." >&2 ; exit 1 ; fi

# Note the quotes around '$TEMP': they are essential!
eval set -- "$TEMP"

export GUI=false
export DEV=false
while true; do
  case "$1" in
    -h | --help ) Help;;
    -g | --gui ) GUI=true; shift ;;
    -d | --dev ) DEV=true; shift ;;
    * ) break ;;
  esac
done

############################################################
# Launch ARTIQ                                             #
############################################################

python --version
artiq_master --version

if $DEV; then
  export MASTER_COMMAND="artiq_master -v --repository . --experiment-subdir repository --log-file log/artiq.log --bind \* --name 'ICL ARTIQ Dev Mode'"
else
  export MASTER_COMMAND="artiq_master -v --git --repository . --experiment-subdir repository --log-file log/artiq.log --bind \* --name 'ICL ARTIQ'"
fi

if $GUI; then
  echo "Launching ARTIQ master + controller + dashboard + backup + database + grafana"
  concurrently \
    -c "green.bold,red.bold,blue.bold,cyan.bold,white.bold,yellow.bold" \
    --kill-others \
    -n master,ctlmgr,dashboard,backup_db,backup_datasets,database,grafana,ndscan \
    --prefix "{name} {time}" \
    --timestamp-format "yyyy-MM-dd HH:mm:ss" \
    "$MASTER_COMMAND" \
    "sleep 5 && artiq_ctlmgr --bind \* -v" \
    "sleep 2 && nix run .#dashboard" \
    "nix run .#backup_database" \
    "nix run .#backup_datasets" \
    "nix run .#database" \
    "nix run .#grafana" \
    "ndscan_dataset_janitor"
else
  echo "Launching ARTIQ master + controller + backup + database + grafana"
  concurrently \
    -c "green.bold,red.bold,cyan.bold,white.bold,yellow.bold" \
    --kill-others \
    -n master,ctlmgr,backup_db,backup_datasets,database,grafana,ndscan \
    --prefix "{name} {time}" \
    --timestamp-format "yyyy-MM-dd HH:mm:ss" \
    "$MASTER_COMMAND" \
    "sleep 5 && artiq_ctlmgr --bind \* -v" \
    "nix run .#backup_database" \
    "nix run .#backup_datasets" \
    "nix run .#database" \
    "nix run .#grafana" \
    "ndscan_dataset_janitor"
fi
