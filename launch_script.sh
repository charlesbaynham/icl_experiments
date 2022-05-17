
python --version
artiq_master --version
echo "Launching ARTIQ master + controller"
concurrently -c red,green --kill-others -n master,ctlmgr "artiq_master -v --experiment-subdir experiments --git --repository ." "sleep 5 && artiq_ctlmgr  -v"
