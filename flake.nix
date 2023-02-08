{
  inputs.pyaion.url = "git+https://gitlab.com/aion-physics/code/artiq/pyaion.git";
  inputs.nixpkgs.follows = "pyaion/nixpkgs";

  inputs.artiq-http.url = "git+https://gitlab.com/aion-physics/code/artiq/drivers/artiq_http.git";
  inputs.artiq-http.inputs.nixpkgs.follows = "nixpkgs";

  inputs.koheron_driver.url = "git+https://gitlab.com/aion-physics/code/artiq/drivers/koheron_ctl200_laser_driver.git";
  inputs.koheron_driver.inputs.nixpkgs.follows = "nixpkgs";

  outputs = { self, nixpkgs, pyaion, flake-utils, artiq-http, koheron_driver }:

    flake-utils.lib.eachDefaultSystem (system:
      let
        requirements = builtins.readFile ./requirements.in;
        generated_outputs = pyaion.lib.${system}.build_institute_outputs
          {
            institute_flake = self;
            system = system;
            extra_requirements = requirements;
            extra_machnix_packages = [ artiq-http.defaultPackage.${system} koheron_driver.defaultPackage.${system} ];
          };
        pkgs = nixpkgs.legacyPackages.${system};

      in
      {
        inherit (generated_outputs) devShells packages formatter;

        apps = generated_outputs.apps // {
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

              exec ${generated_outputs.apps.grafana.program}
            '');
          };


          full_stack =
            let
              backup_database = "nix run .#backup_database";
              backup_datasets = "nix run .#backup_datasets";
            in
            generated_outputs.apps.full_stack.override (prev: {
              commands = prev.commands // {
                inherit backup_database backup_datasets;
              };
            });
        };

        nixConfig = {
          bash-prompt = "\\[\\e[1m\\e[32m\\]ICL ARTIQ \\[\\e[0m\\e[94m\\](\\w)\\[\\e[0m\\] $ ";
        };
      });
}
