
python --version
artiq_master --version
echo "Launching ARTIQ master + controller in development mode"
concurrently \
  -c "green.bold,red.bold" \
  --kill-others \
  -n master,ctlmgr \
  --prefix "{name} {time}" \
  --timestamp-format "yyyy-MM-dd HH:mm:ss" \
  "artiq_master -v --repository . --experiment-subdir repository --log-file log/artiq.log" \
  "sleep 5 && artiq_ctlmgr -v"
