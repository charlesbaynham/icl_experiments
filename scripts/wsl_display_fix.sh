#!/bin/bash

# This script detects if we are
# a) Running WSL
# b) and have an XTerm server running on the Windows host (e.g. MobaXTerm)
#
# If so, it sets the DISPLAY variable to use the Windows XServer instead of the local one

# Step 1: Detect WSL
if ! grep -qi microsoft /proc/version; then
    echo "Not running inside WSL. Exiting."
    return 1 2>/dev/null || exit 1
fi

# Step 2: Get Windows host IP from default route (WSL2-compatible)
WIN_IP=$(ip route | awk '/default/ {print $3}')
if [[ -z "$WIN_IP" ]]; then
    echo "Could not determine Windows host IP."
    return 1 2>/dev/null || exit 1
fi

# Step 3: Check if X server is running on Windows host
if nc -w 1 -z "$WIN_IP" 6000; then
    export DISPLAY="$WIN_IP:0"
    echo "✅ X server detected at $WIN_IP:0"
    echo "DISPLAY set to $DISPLAY"
else
    echo "❌ No X server detected on $WIN_IP:6000"
fi
