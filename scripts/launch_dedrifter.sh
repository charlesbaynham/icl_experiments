#!/usr/bin/bash

# Update the startup & idle kernels for the dedrifter, then write the config and
# sync timestamps. Note that there is currently a bug which prevents you from
# updating the config when the dedrifter is already running. This script
# therefore reboots the crate to work around the bug.

# Update the startup and idle kernels
echo "Updating startup kernel..."
artiq_compile \
    --device-db dedrifter/dedrifter_device_db.py \
    dedrifter/startup_kernel.py

artiq_coremgmt \
    --device-db dedrifter/dedrifter_device_db.py \
    config write -f startup_kernel dedrifter/startup_kernel.elf


# Update the idle kernel
echo "Updating idle kernel..."

artiq_compile \
    --device-db dedrifter/dedrifter_device_db.py \
    dedrifter/idle_kernel_dedrifter.py

artiq_coremgmt \
    --device-db dedrifter/dedrifter_device_db.py \
    config write -f idle_kernel dedrifter/idle_kernel_dedrifter.elf


# Reboot the crate
echo "Rebooting the crate to unload the CoreCache. This is a workaround..."
artiq_coremgmt \
    --device-db dedrifter/dedrifter_device_db.py \
    reboot
sleep 10

# Sync timestamps and write the config
echo "Syncing timestamps and writing config..."
artiq_run \
    --device-db dedrifter/dedrifter_device_db.py \
    dedrifter/update_dedrifter.py

echo "Done."
