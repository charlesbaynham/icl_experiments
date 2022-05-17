
python --version
artiq_master --version
echo "Launching ARTIQ master + controller"
concurrently --kill-others -n master,ctlmgr "artiq_master --git --repository ." "artiq_ctlmgr"