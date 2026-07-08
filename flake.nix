{
  inputs.pyaion.url = "git+https://gitlab.com/aion-physics/code/artiq/pyaion.git";
  inputs.nixpkgs.follows = "pyaion/nixpkgs";

  # TODO: Go back to pyaion artiq. This needs an ARTIQ update - see MR
  # Pinned to the make-event-spreading-optional base (e98dbf5) plus the head-hack
  # "WORKING" working-tree-rev commits, which sit directly on top of that base.
  inputs.alt_artiq.url = "git+https://gitlab.com/aion-physics/code/artiq/forks/artiq_fork.git?ref=feature/working-tree-rev";
  inputs.alt_artiq.inputs.nixpkgs.follows = "nixpkgs";
  inputs.pyaion.inputs.artiq.follows = "alt_artiq";

  inputs.git-hooks.url = "github:cachix/git-hooks.nix";

  # Independent nixpkgs pin used ONLY to provide an up-to-date Grafana. It does
  # not "follows" anything, so updating it never perturbs the ARTIQ/Python
  # closure. Grafana is a standalone Go binary that nothing else depends on.
  inputs.nixpkgs-grafana.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs = {
    self,
    nixpkgs,
    nixpkgs-grafana,
    flake-utils,
    pyaion,
    git-hooks,
    ...
  }: let
    # Configure ARTIQ services to bind to the labserver's AION IP address.
    # This is so that the server can run other ARTIQ sessions bound to other
    # IP addresses.
    bind_settings = {
      bind_command = "--no-localhost-bind --bind 10.137.1.252";
      connection_ip = "10.137.1.252";
    };
  in
    flake-utils.lib.eachSystem ["x86_64-linux"] (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      callPackage = pyaion.lib.${system}.callPackage;

      # Grafana pinned to the latest stable nixpkgs release, independent of the
      # rest of the stack. See the nixpkgs-grafana input above.
      grafanaPkg = nixpkgs-grafana.legacyPackages.${system}.grafana;

      # Build the python bindings for aravis
      python-aravis = callPackage ./nix/aravis/python-aravis.nix {};

      originalOutputs =
        pyaion.lib.${system}.artiq_flake_builder {poetry_app = self;};
      overriddenOutputs = originalOutputs.override (prev: {
        extra-build-requirements = {
          artiq-http = ["setuptools"];
          koheron-ctl200-laser-driver = ["poetry-core"];
          qbutler = ["poetry-core"];
          aravis = ["setuptools"];
          pygobject = ["setuptools"];
          pyft232 = ["setuptools"];
          python-vxi11 = ["setuptools"];
          tenma-power-supply = ["poetry-core"];
          toptica-wrapper = ["poetry-core"];
          wand = ["poetry-core"];
          gaio-laser-driver = ["poetry-core"];
          relocker-driver = ["poetry-core"];
          andor-artiq-ndsp = ["poetry-core"];
          imperial-artiq-applets = ["poetry-core"];
        };
        extra-overrides = [
          # Patch python-aravis to use poetry-resolved dependencies
          (final: prev: {
            aravis = python-aravis.overridePythonAttrs {
              propagatedBuildInputs =
                prev.aravis.propagatedBuildInputs
                ++ [pkgs.aravis];
            };
            # Annoyingly pygobject3 depends on pycairo which also requires special treatment.
            # Fortunately nixpkgs has handled this. So:
            pycairo = pkgs.python3Packages.pycairo.overridePythonAttrs {
              # the nixpkgs derivation has "meson" in the nativeBuildInputs
              # but poetry puts it in "propagatedBuildInputs". This would
              # cause a clash so:
              nativeBuildInputs = [];
              propagatedBuildInputs = prev.pycairo.propagatedBuildInputs;
            };
            relocker-driver = prev.relocker-driver.overridePythonAttrs {
              dontWrapQtApps = true;
            };
            pylablib =
              prev.pylablib.overridePythonAttrs {dontWrapQtApps = true;};
            andor-artiq-ndsp = prev.andor-artiq-ndsp.overridePythonAttrs {
              dontWrapQtApps = true;
            };
            imperial-artiq-applets = prev.imperial-artiq-applets.overridePythonAttrs {
              dontWrapQtApps = true;
            };
            numba = prev.numba.override {preferWheel = false;};
            pyusb = prev.pyusb.override {preferWheel = false;};

            # Our fork of wand used poetry for packaging, so we don't need
            # to worry about deps. But it does have a graphical interface
            # which needs patching:
            wand = prev.wand.overridePythonAttrs {
              nativeBuildInputs =
                prev.wand.nativeBuildInputs
                ++ [pkgs.qt5.wrapQtAppsHook];
              dontWrapQtApps = true;
              postFixup = ''
                wrapQtApp "$out/bin/wand_gui"
              '';
            };
          })
        ];
      });

      wand_gui_launcher = let
        config_file = "${self}/scripts/icl_aion_gui_config.pyon";
      in (pkgs.writeShellScriptBin "icl_wand" ''
        export PATH=${
          pkgs.lib.makeBinPath overriddenOutputs.devShells.artiq.buildInputs
        }:$PATH

        export WAND_CONFIG_PATH=$(mktemp -t wand_server_XXXXXXXX)
        cp "${config_file}" "$WAND_CONFIG_PATH"
        exec wand_gui -n icl_aion "$@"
      '');

      # Dashboard launcher for the ICL AION address
      dashboard_launcher = pkgs.writeShellScriptBin "icl_dashboard" ''
        # If you want to reset the dashboard settings each time, uncomment this line
        # export XDG_CONFIG_HOME=$(mktemp -d)

        export PYTHONPATH=${self}:$PYTHONPATH
        exec ${overriddenOutputs.apps.dashboard.program} -s ${bind_settings.connection_ip}
      '';

      # Rebuild the auto-generated stub catalog the master serves, and print the
      # path of the resulting worktree (see scripts/refresh_stubs.sh). Operates
      # on the current working directory's git repo, so run it from the repo root.
      refresh_stubs_launcher = pkgs.writeShellScriptBin "refresh_stubs" ''
        export PATH=${
          pkgs.lib.makeBinPath (overriddenOutputs.devShells.artiq.buildInputs
            ++ [pkgs.git])
        }:$PATH
        exec ./scripts/refresh_stubs.sh "$@"
      '';
    in {
      inherit (overriddenOutputs) formatter;

      # Add pre-commit hooks and WSL display fix to the default shell. The
      # pre-commit / git-hooks machinery lives in ./nix/precommit.nix.
      devShells = let
        precommit = import ./nix/precommit.nix {
          inherit pkgs;
          patchedPreCommit = git-hooks.packages.${system}.pre-commit;
          preCommitCheck = self.checks.${system}.pre-commit-check;
        };

        newDefaultShell =
          overriddenOutputs.devShells.default.overrideAttrs
          (prev: {
            shellHook =
              ''
                source ${self}/scripts/wsl_display_fix.sh
                source ${self}/scripts/gitlab_ssh_rewrite.sh
              ''
              + precommit.shellHook;
          });
      in
        overriddenOutputs.devShells // {default = newDefaultShell;};

      packages =
        overriddenOutputs.packages
        // {
          default = dashboard_launcher;
          dashboard = dashboard_launcher;
          wand = wand_gui_launcher;
        };

      checks = {
        # Pre-commit formatting. see
        # https://devenv.sh/reference/options/#pre-commithooks for a list of
        # options
        pre-commit-check = git-hooks.lib.${system}.run {
          src = ./.;
          hooks = {
            alejandra.enable = true;
            autoflake.enable = true;
            autoflake.args = [
              "--remove-all-unused-imports"
              "--remove-unused-variables"
              "--in-place"
            ];
            black.enable = true;
            check-case-conflicts.enable = true;
            check-merge-conflicts.enable = true;
            check-yaml.enable = true;
            end-of-file-fixer.enable = true;
            isort.enable = true;
            isort.args = ["--profile" "black" "--force-single-line-imports"];
            mixed-line-endings.enable = true;
            prettier.enable = true;
            taplo.enable = true;
            trim-trailing-whitespace.enable = true;
          };
        };
      };

      apps =
        overriddenOutputs.apps
        // {
          refresh_stubs = {
            type = "app";
            program = "${refresh_stubs_launcher}/bin/refresh_stubs";
          };

          backup_datasets = let
            script = pkgs.writeShellScriptBin "run" ''
              export PATH=${
                pkgs.lib.makeBinPath [pkgs.rsync pkgs.sshpass]
              }:$PATH

              # Unlike the other scripts, this one is launched w.r.t. the working directory
              # so that if the working dir isn't correct, it'll fail with an error message
              # rather than looking like it's working and then not actually backing up the data.
              exec ./scripts/backup_datasets.sh
            '';
          in {
            type = "app";
            program = "${script}/bin/run";
          };

          backup_database = let
            script = pkgs.writeShellScriptBin "run" ''
              export PATH=${pkgs.lib.makeBinPath [pkgs.influxdb]}:$PATH

              exec ${self}/scripts/backup_database.sh
            '';
          in {
            type = "app";
            program = "${script}/bin/run";
          };

          backup_grafana = let
            script = pkgs.writeShellScriptBin "run" ''
              export PATH=${
                pkgs.lib.makeBinPath [
                  pkgs.sqlite
                  pkgs.gnutar
                  pkgs.gzip
                  pkgs.coreutils
                  pkgs.rsync
                  pkgs.sshpass
                  pkgs.openssh
                ]
              }:$PATH

              exec ${self}/scripts/backup_grafana.sh
            '';
          in {
            type = "app";
            program = "${script}/bin/run";
          };

          check_for_fixme = let
            script = pkgs.writeShellScriptBin "run" ''
              export PATH=${pkgs.lib.makeBinPath [pkgs.ripgrep]}:$PATH

              if rg FIXME "${self}" -g "!nix" -g !flake.nix -g !readme.rst -g !AGENTS.md -g "!archived_experiments"; then
                echo \"FIXME\" found in files
                exit 1
              else
                echo No \"FIXME\"s found
                exit 0
              fi

            '';
          in {
            type = "app";
            program = "${script}/bin/run";
          };

          dedrifter = let
            script = pkgs.writeShellScriptBin "dedrifter" ''
              export PATH=${
                pkgs.lib.makeBinPath
                overriddenOutputs.devShells.artiq.buildInputs
              }:$PATH

              # Copy the source code to a temporary directory that is writeable
              export DEDRIFTER_SOURCE_DIR=$(mktemp -d -t dedrifter_source_XXXXXXXX)
              cp -r "${self}/." "$DEDRIFTER_SOURCE_DIR"

              # Make everything writable
              chmod -R u+w "$DEDRIFTER_SOURCE_DIR"

              # Change to the source directory
              cd "$DEDRIFTER_SOURCE_DIR"

              # Add this dir to PYTHONPATH
              export PYTHONPATH="$DEDRIFTER_SOURCE_DIR:$PYTHONPATH"

              # Run the dedrifter script
              exec ${self}/scripts/launch_dedrifter.sh "$@"
            '';
          in {
            type = "app";
            program = "${script}/bin/dedrifter";
          };

          # Grafana is pinned to the latest stable nixpkgs (see the
          # nixpkgs-grafana input) rather than pyaion's old nixpkgs. We inline
          # the full wrapper here instead of delegating to
          # overriddenOutputs.apps.grafana.program because modern Grafana
          # dropped the standalone "grafana-server" binary in favour of the
          # "grafana server" subcommand. The provisioning config is still
          # reused from pyaion.
          grafana = flake-utils.lib.mkApp {
            drv = pkgs.writeShellScriptBin "script" ''
              # Add some grafana config
              export GF_DEFAULT_INSTANCE_NAME=aion-icl-grafana
              export GF_AUTH_ANONYMOUS_ORG_NAME=Imperial_USL
              export GF_AUTH_ANONYMOUS_ENABLED=true

              # Configure for internal Imperial email alerting
              export GF_SMTP_ENABLED=true
              export GF_SMTP_HOST=automail.cc.ic.ac.uk:25
              export GF_SMTP_FROM_ADDRESS=grafana@aionlabserver.ph.ic.ac.uk

              export GF_PATHS_PROVISIONING=${pyaion}/nix/grafana_provisioning

              # Configure grafana data storage locations
              export GF_PATHS_DATA=~/.grafana/data
              export GF_PATHS_LOGS=~/.grafana/logs
              export GF_PATHS_PLUGINS=~/.grafana/plugins

              exec ${grafanaPkg}/bin/grafana server --homepath ${grafanaPkg}/share/grafana
            '';
          };

          default = flake-utils.lib.mkApp {drv = dashboard_launcher;};

          wand = flake-utils.lib.mkApp {drv = wand_gui_launcher;};

          wand_server = flake-utils.lib.mkApp {
            drv = let
              config_file = "${self}/scripts/icl_aion_server_config.pyon";
            in (pkgs.writeShellScriptBin "script" ''
              export PATH=${
                pkgs.lib.makeBinPath
                overriddenOutputs.devShells.artiq.buildInputs
              }:$PATH

              export WAND_CONFIG_PATH=$(mktemp -t wand_server_XXXXXXXX)
              cp "${config_file}" "$WAND_CONFIG_PATH"
              exec wand_server "$@"
            '');
          };

          artiq = overriddenOutputs.apps.artiq.override (prev: bind_settings);

          full_stack = let
            backup_database = "nix run .#backup_database";
            backup_datasets = "nix run .#backup_datasets";
            backup_grafana = "nix run .#backup_grafana";

            # This is an extra instance of ctlmgr which searches for controllers assigned to
            # bind_settings.connection_ip instead of "::1". This is only relevant for moninj
            # since we must hard-code the IP of the labserver in the moninj proxy otherwise
            # dashboards don't know where to connect to it.
            moninj_proxy_ctlmgr = "sleep 120 && artiq_ctlmgr  --server ${bind_settings.connection_ip} --bind \\* -v --host-filter ${bind_settings.connection_ip} --port-control 32490";

            # Automatic startup of database monitors. Pin -r master: the served
            # repository is the stub catalog, so an unpinned -R submit would run
            # the MonitorMaster *stub* (a no-op that raises NotImplementedError).
            monitor_launcher = "sleep 120 && artiq_client -s ${bind_settings.connection_ip} submit -p monitors -P -10 -R -r master --flush -c MonitorMaster repository/monitors/monitor_master.py && sleep infinity";

            # Serve the experiment catalog from the auto-generated stub worktree
            # rather than the launch checkout, so the dashboard lists experiments
            # from every branch in stubs_sources.yaml. device_db is untouched: the
            # master still loads it from the launch cwd (no --device-db here), and
            # real experiments are launched by submitting with a real repository
            # revision (a branch name), which resolves against the shared object DB.
            artiq_master = ''
              set -e
              STUBS_WT="$(${refresh_stubs_launcher}/bin/refresh_stubs)"
              exec artiq_master \
                --verbose \
                --git \
                --repository "$STUBS_WT" \
                --experiment-subdir repository \
                --log-file log/artiq.log \
                $ARTIQ_COMMANDLINE_ADDITIONS \
                --name 'AION ARTIQ'
            '';
          in
            overriddenOutputs.apps.full_stack.override (prev:
              {
                commands =
                  prev.commands
                  // {
                    inherit
                      artiq_master
                      backup_database
                      backup_datasets
                      backup_grafana
                      moninj_proxy_ctlmgr
                      monitor_launcher
                      ;
                    ndscan_janitor = "sleep 120 && ndscan_dataset_janitor --timeout 7200 --server ${bind_settings.connection_ip}"; # 2 hours
                  };
              }
              // bind_settings);
        };
    })
    // {
      inherit bind_settings;
    };
}
