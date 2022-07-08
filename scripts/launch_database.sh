# Non-default InfluxDB configuration
export INFLUXDB_AUTH_ENABLED=false
export INFLUXDB_FLUX_ENABLED=true

# Configure the InfluxBD data storage locations
# These are the default settings, but are written out here to be explicit
export INFLUXDB_META_DIR=~/.influxdb/meta
export INFLUXDB_DATA_DIR=~/.influxdb/data
export INFLUXDB_DATA_WAL_DIR=~/.influxdb/wal

# Wait two seconds (enough time for the server to start) then create a new
# database called "db" if it does not already exist
(sleep 2; curl -XPOST 'http://localhost:8086/query' --data-urlencode 'q=CREATE DATABASE "db"') &

# Pass control to influxd
exec influxd
