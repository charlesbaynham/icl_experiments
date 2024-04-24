{
  inputs.pyaion.url = "git+https://gitlab.com/aion-physics/code/artiq/pyaion.git";
  inputs.nixpkgs.follows = "pyaion/nixpkgs";

  # FIXME: Go back to pyaion artiq
  inputs.alt_artiq.url = "git+https://gitlab.com/aion-physics/code/artiq/forks/artiq_fork.git?ref=icl";
  inputs.alt_artiq.inputs.nixpkgs.follows = "nixpkgs";
  inputs.pyaion.inputs.artiq.follows = "alt_artiq";

  outputs = { self, nixpkgs, flake-utils, pyaion, ... }:
    flake-utils.lib.eachSystem [ "x86_64-linux" ]
      (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          callPackage = pyaion.lib.${system}.callPackage;

          # Build the python bindings for aravis
          python-aravis = callPackage ./nix/aravis/python-aravis.nix { };

          originalOutputs = pyaion.lib.${system}.artiq_flake_builder {
            poetry_app = self;
            extra_non_python_deps = [ pkgs.ripgrep ];
          };
          overriddenOutputs = originalOutputs.override (prev: {
            extra-build-requirements = {
              artiq-http = [ "setuptools" ];
              koheron-ctl200-laser-driver = [ "poetry-core" ];
              qbutler = [ "setuptools" ];
              aravis = [ "setuptools" ];
              pygobject = [ "setuptools" ];
              tenma-power-supply = [ "poetry-core" ];
              toptica-wrapper = [ "poetry-core" ];
              wand = [ "poetry-core" ];
            };
            extra-overrides = [
              # Patch python-aravis to use poetry-resolved dependencies
              (final: prev: {
                aravis = python-aravis.overridePythonAttrs {
                  propagatedBuildInputs = prev.aravis.propagatedBuildInputs ++ [ pkgs.aravis ];
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

                # Our fork of wand used poetry for packaging, so we don't need
                # to worry about deps. But it does have a graphical interface
                # which needs patching:
                wand = prev.wand.overridePythonAttrs {
                  nativeBuildInputs = prev.wand.nativeBuildInputs ++ [ pkgs.qt5.wrapQtAppsHook ];
                  dontWrapQtApps = true;
                  postFixup = ''
                    wrapQtApp "$out/bin/wand_gui"
                  '';
                };
              })
            ];
          });

        in
        {
          inherit (overriddenOutputs) packages formatter devShells;

          apps = overriddenOutputs.apps // {
            backup_datasets =
              let
                script = pkgs.writeShellScriptBin "run" ''
                  export PATH=${pkgs.lib.makeBinPath [pkgs.rsync]}:$PATH

                  # Unlike the other scripts, this one is launched w.r.t. the working directory
                  # so that if the working dir isn't correct, it'll fail with an error message
                  # rather than looking like it's working and then not actuall backing up the data.
                  exec ./scripts/backup_datasets.sh
                '';
              in
              { type = "app"; program = "${script}/bin/run"; };

            backup_database =
              let
                script = pkgs.writeShellScriptBin "run" ''
                  export PATH=${pkgs.lib.makeBinPath [pkgs.influxdb]}:$PATH

                  exec ${self}/scripts/backup_database.sh
                '';
              in
              { type = "app"; program = "${script}/bin/run"; };

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

            # Temporary hack to get the dashboard to launch with "nix run" and
            # default to ICL's settings
            default = flake-utils.lib.mkApp {
              drv = (pkgs.writeShellScriptBin "script" ''
                exec ${overriddenOutputs.apps.dashboard.program} -s ph-cb2409-2.ph.ic.ac.uk
              '');
            };

            wand = flake-utils.lib.mkApp {
              drv =
                let config_file = "${self}/scripts/icl_aion_gui_config.pyon";
                in
                (pkgs.writeShellScriptBin "script" ''
                  export PATH=${pkgs.lib.makeBinPath overriddenOutputs.devShells.artiq.buildInputs}:$PATH

                  export WAND_CONFIG_PATH=$(mktemp -t wand_server_XXXXXXXX)
                  cp "${config_file}" "$WAND_CONFIG_PATH"
                  exec wand_gui -n icl_aion "$@"
                '');
            };

            wand_server = flake-utils.lib.mkApp {
              drv =
                let config_file = "${self}/scripts/icl_aion_server_config.pyon";
                in
                (pkgs.writeShellScriptBin "script" ''
                  export PATH=${pkgs.lib.makeBinPath overriddenOutputs.devShells.artiq.buildInputs}:$PATH

                  export WAND_CONFIG_PATH=$(mktemp -t wand_server_XXXXXXXX)
                  cp "${config_file}" "$WAND_CONFIG_PATH"
                  exec wand_server "$@"
                '');
            };

            full_stack =
              let
                backup_database = "nix run .#backup_database";
                backup_datasets = "nix run .#backup_datasets";

                # This is an extra instance of ctlmgr which searches for controllers assigned to "10.137.1.252" instead of "::1"
                # This is only relevant for moninj since we must hard-code the IP of the labserver in the moninj proxy otherwise dashboards
                # don't know where to connect to it.
                moninj_proxy_ctlmgr = "sleep 5 && artiq_ctlmgr --bind \\\* -v --host-filter 10.137.1.252 --port-control 32490";
              in
              overriddenOutputs.apps.full_stack.override (prev: {
                commands = prev.commands // {
                  inherit backup_database backup_datasets moninj_proxy_ctlmgr;
                  ndscan_janitor = "ndscan_dataset_janitor --timeout 7200"; # 2 hours
                };
              });
          };
        }
      );
}
