---
name: nix-setup
description: Use when Nix is not available in the current environment (e.g. a fresh Claude Code cloud container) and you need it to run tests, build the artiq environment, or use any `nix run` / `nix develop` command from this repository.
---

# Setting up Nix in an ephemeral container

For agent sandboxes / fresh containers with no systemd (e.g. Claude Code
cloud sessions). The aion-physics Cachix cache makes this fast: the full
artiq environment downloads in a few minutes instead of building for hours.

Check first: `command -v nix` — if Nix is already installed, skip to making
sure the daemon is running and `PATH` is set (steps 3 onwards).

As root:

```bash
# 1. Install Determinate Nix without an init system
curl -fsSL -o /tmp/nix-install https://install.determinate.systems/nix
sh /tmp/nix-install install linux --init none --no-confirm \
    --extra-conf "experimental-features = nix-command flakes"
# (the installer's shell self-test fails because no daemon is running yet -
# this is expected and harmless)

# 2. Register the aion-physics Cachix cache (pre-built artiq environment,
#    populated by the GitLab CI)
cat >> /etc/nix/nix.conf <<'EOF'
extra-substituters = https://aion-physics.cachix.org
extra-trusted-public-keys = aion-physics.cachix.org-1:6nSnNuBFRf4kl9EPG6hAMQHBjcrrKEfHG2BpHBE2DVs=
EOF

# 3. Start the daemon by hand (no systemd in containers) and set PATH
nohup /nix/var/nix/profiles/default/bin/nix-daemon >/tmp/nix-daemon.log 2>&1 &
export PATH=/nix/var/nix/profiles/default/bin:$PATH

# 4. Smoke test - the first invocation downloads the environment (~5 min)
nix run .#pytest -- tests/test_basics.py -q
```

Notes:

- The flake's GitLab inputs (pyaion, the artiq fork) are publicly readable,
  so no credentials are needed to fetch them.
- `PATH` does not persist between shells: re-export
  `/nix/var/nix/profiles/default/bin` (or source
  `/nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh`) in each new
  shell, and check the daemon is still up with `pgrep -f nix-daemon`.
- The environment closure is several GB; check disk space (`df -h /`) before
  starting if the container is small.
- Once `nix run` has executed inside the repository, git-hooks.nix installs
  the real pre-commit hooks into `.git/hooks`, so subsequent local commits
  get the same lint gate as CI.

To run tests once Nix works, see the `running-tests` skill.
