{
  inputs.pyaion.url =
    "git+https://gitlab.com/aion-physics/code/artiq/pyaion.git";
  inputs.nixpkgs.follows = "pyaion/nixpkgs";

  # TODO: Go back to pyaion artiq. This is currently hard because we're getting
  # sequence errors coming from somewhere in the red MOT sequence when we
  # update. It's not clear why
  inputs.alt_artiq.url =
    "git+https://gitlab.com/aion-physics/code/artiq/forks/artiq_fork.git?ref=make-event-spreading-optional";
  inputs.alt_artiq.inputs.nixpkgs.follows = "nixpkgs";
  inputs.pyaion.inputs.artiq.follows = "alt_artiq";

  outputs = { self, nixpkgs, flake-utils, pyaion, ... }:
    flake-utils.lib.eachSystem [ "x86_64-linux" ] (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        callPackage = pyaion.lib.${system}.callPackage;

        # Build the python bindings for aravis
        python-aravis = callPackage ./nix/aravis/python-aravis.nix { };

        originalOutputs =
          pyaion.lib.${system}.artiq_flake_builder { poetry_app = self; };
        overriddenOutputs = originalOutputs.override (prev: {
          extra-build-requirements = {
            artiq-http = [ "setuptools" ];
            koheron-ctl200-laser-driver = [ "poetry-core" ];
            qbutler = [ "setuptools" ];
            aravis = [ "setuptools" ];
            pygobject = [ "setuptools" ];
            pyft232 = [ "setuptools" ];
            python-vxi11 = [ "setuptools" ];
            tenma-power-supply = [ "poetry-core" ];
            toptica-wrapper = [ "poetry-core" ];
            wand = [ "poetry-core" ];
            relocker-driver = [ "poetry-core" ];
            andor-artiq-ndsp = [ "poetry-core" ];
            imperial-artiq-applets = [ "poetry-core" ];
          };
          extra-overrides = [
            # Patch python-aravis to use poetry-resolved dependencies
            (final: prev: {
              aravis = python-aravis.overridePythonAttrs {
                propagatedBuildInputs = prev.aravis.propagatedBuildInputs
                  ++ [ pkgs.aravis ];
              };
              # Annoyingly pygobject3 depends on pycairo which also requires special treatment.
              # Fortunately nixpkgs has handled this. So:
              pycairo = pkgs.python3Packages.pycairo.overridePythonAttrs {
                # the nixpkgs derivation has "meson" in the nativeBuildInputs
                # but poetry puts it in "propagatedBuildInputs". This would
                # cause a clash so:
                nativeBuildInputs = [ ];
                propagatedBuildInputs = prev.pycairo.propagatedBuildInputs;
              };
              relocker-driver = prev.relocker-driver.overridePythonAttrs {
                dontWrapQtApps = true;
              };
              pylablib =
                prev.pylablib.overridePythonAttrs { dontWrapQtApps = true; };
              andor-artiq-ndsp = prev.andor-artiq-ndsp.overridePythonAttrs {
                dontWrapQtApps = true;
              };
              imperial-artiq-applets =
                prev.imperial-artiq-applets.overridePythonAttrs {
                  dontWrapQtApps = true;
                };
              numba = prev.numba.override { preferWheel = false; };
              pyusb = prev.pyusb.override { preferWheel = false; };

              # Our fork of wand used poetry for packaging, so we don't need
              # to worry about deps. But it does have a graphical interface
              # which needs patching:
              wand = prev.wand.overridePythonAttrs {
                nativeBuildInputs = prev.wand.nativeBuildInputs
                  ++ [ pkgs.qt5.wrapQtAppsHook ];
                dontWrapQtApps = true;
                postFixup = ''
                  wrapQtApp "$out/bin/wand_gui"
                '';
              };
            })
          ];
        });

        wand_gui_launcher =
          let config_file = "${self}/scripts/icl_aion_gui_config.pyon";

          in (pkgs.writeShellScriptBin "icl_wand" ''
            export PATH=${
              pkgs.lib.makeBinPath overriddenOutputs.devShells.artiq.buildInputs
            }:$PATH

            export WAND_CONFIG_PATH=$(mktemp -t wand_server_XXXXXXXX)
            cp "${config_file}" "$WAND_CONFIG_PATH"
            exec wand_gui -n icl_aion "$@"
          '');

        # Configure ARTIQ services to bind to the labserver's AION IP address.
        # This is so that the server can run other ARTIQ sessions bound to other
        # IP addresses.
        bind_settings = {
          bind_command = "--no-localhost-bind --bind 10.137.1.252";
          connection_ip = "10.137.1.252";
        };

        # Dashboard launcher for the ICL AION address
        dashboard_launcher = (pkgs.writeShellScriptBin "icl_dashboard" ''
          # If you want to reset the dashboard settings each time, uncomment this line
          # export XDG_CONFIG_HOME=$(mktemp -d)

          exec ${overriddenOutputs.apps.dashboard.program} -s ${bind_settings.connection_ip}
        '');

      in {
        inherit (overriddenOutputs) formatter devShells;

        packages = overriddenOutputs.packages // {
          default = dashboard_launcher;
          dashboard = dashboard_launcher;
          wand = wand_gui_launcher;
        };

        apps = overriddenOutputs.apps // {
          backup_datasets = let
            script = pkgs.writeShellScriptBin "run" ''
              export PATH=${pkgs.lib.makeBinPath [ pkgs.rsync ]}:$PATH

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
              export PATH=${pkgs.lib.makeBinPath [ pkgs.influxdb ]}:$PATH

              exec ${self}/scripts/backup_database.sh
            '';
          in {
            type = "app";
            program = "${script}/bin/run";
          };

          check_for_fixme = let
            script = pkgs.writeShellScriptBin "run" ''
              export PATH=${pkgs.lib.makeBinPath [ pkgs.ripgrep ]}:$PATH

              if rg FIXME "${self}" -g "!nix" -g !flake.nix -g !readme.rst; then
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

          grafana = flake-utils.lib.mkApp {
            drv = (pkgs.writeShellScriptBin "script" ''
              # Add some grafana config
              export GF_DEFAULT_INSTANCE_NAME=aion-icl-grafana
              export GF_AUTH_ANONYMOUS_ORG_NAME=Imperial_USL
              export GF_AUTH_ANONYMOUS_ENABLED=true

              # Configure for internal Imperial email alerting
              export GF_SMTP_ENABLED=true
              export GF_SMTP_HOST=automail.cc.ic.ac.uk:25
              export GF_SMTP_FROM_ADDRESS=grafana@aionlabserver.ph.ic.ac.uk

              exec ${overriddenOutputs.apps.grafana.program}
            '');
          };

          default = flake-utils.lib.mkApp { drv = dashboard_launcher; };

          wand = flake-utils.lib.mkApp { drv = wand_gui_launcher; };

          wand_server = flake-utils.lib.mkApp {
            drv =
              let config_file = "${self}/scripts/icl_aion_server_config.pyon";
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

            # Automatic startup of database monitors
            monitor_launcher =
              "sleep 200 && artiq_client submit -p monitors -P -10 -R --flush -c MonitorMaster repository/monitors/monitor_master.py && sleep infinity";

          in overriddenOutputs.apps.full_stack.override (prev:
            {
              commands = prev.commands // {
                inherit backup_database backup_datasets monitor_launcher;
              };
            } // bind_settings);
        };
      });
}
