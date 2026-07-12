#!/usr/bin/env bash
# Start the AION ARTIQ stack inside a detached tmux session named "aion".
#
# This is the entry point used both by an operator running it by hand and by
# the "aion-artiq.service" systemd unit (installed with `nix run .#install_systemd`).
# It is safe to run repeatedly: if the session already exists it does nothing.

set -euo pipefail

SESSION=aion
REPO_DIR=/root/icl_experiments

# When launched from a minimal environment (e.g. systemd on boot) the Nix
# profile is not sourced automatically, so `nix` would not be on PATH. Source
# whichever profile script exists so that ./run_artiq.sh can find `nix`.
if [ -e /etc/profile.d/nix.sh ]; then
  # shellcheck disable=SC1091
  . /etc/profile.d/nix.sh
elif [ -e /etc/profile.d/nix-daemon.sh ]; then
  # shellcheck disable=SC1091
  . /etc/profile.d/nix-daemon.sh
elif [ -e "${HOME:-/root}/.nix-profile/etc/profile.d/nix.sh" ]; then
  # shellcheck disable=SC1091
  . "${HOME:-/root}/.nix-profile/etc/profile.d/nix.sh"
fi

# Don't start a second session if one is already running. This keeps the
# script idempotent and means re-running the installer never disturbs a
# session that an operator is already using.
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "tmux session '$SESSION' is already running; nothing to do."
  exit 0
fi

tmux new-session -d -s "$SESSION" -c "$REPO_DIR" './run_artiq.sh'
echo "Started tmux session '$SESSION'. Attach with: tmux attach -t $SESSION"
