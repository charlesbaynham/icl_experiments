# Configure grafana data storage locations
export GF_PATHS_DATA=~/.grafana/data
export GF_PATHS_LOGS=~/.grafana/logs
export GF_PATHS_PLUGINS=~/.grafana/plugins

# Add some grafana config
export GF_DEFAULT_INSTANCE_NAME=aion-icl-grafana
export GF_AUTH_ANONYMOUS_ORG_NAME=Imperial_USL
export GF_AUTH_ANONYMOUS_ENABLED=true

# Configure for internal Imperial email alerting
export GF_SMTP_ENABLED=true
export GF_SMTP_HOST=automail.cc.ic.ac.uk:25
export GF_SMTP_FROM_ADDRESS=grafana@aionlabserver.ph.ic.ac.uk

# Launch
exec grafana-server --homepath "$GRAFANA_HOMEPATH"
