{
  inputs = {
    artiq.url = "git+ssh://git@gitlab.com/aion-physics/code/artiq/forks/artiq_fork.git";
    nixpkgs.follows = "artiq/nixpkgs";
  };

  outputs = { self, artiq, nixpkgs }:
    let
      x = 123;
    in rec {
      pkgs = import nixpkgs { system = "x86_64-linux"; };
    

      # Define the requirements for the ARTIQ environment.
      # These are used both for the devShell (launched with `nix develop`)
      # and the running app (launched with `nix run`)
      requirements = [
        (pkgs.python3.withPackages(ps: [
          artiq.packages.x86_64-linux.artiq
          ps.numpy ps.ipython ps.jupyter ps.pip
        ]))
        pkgs.concurrently
      ];

      # Define a default app, to be run by "nix run"
      # We have to manually define the PATH variable
      script = pkgs.writeShellScriptBin "artiq-launcher" ''
          export PATH=${pkgs.lib.makeBinPath requirements}:$PATH

          echo "Launching ARTIQ master + controller"
          python --version
          artiq_master --version
          concurrently --kill-others -n master,ctlmgr artiq_master artiq_ctlmgr
        '';
    # in rec {
      
      # This launches an artiq_master + artiq_controller session
      apps.x86_64-linux.artiq = {
        type = "app";
        program = "${script}/bin/artiq-launcher";
      };
      apps.x86_64-linux.default = apps.x86_64-linux.artiq;

      devShells.x86_64-linux.default = devShells.x86_64-linux.artiq;

      devShells.x86_64-linux.artiq = pkgs.mkShell {
        name = "icl-artiq-environment";
        buildInputs = requirements;
      };

      devShells.x86_64-linux.flash = pkgs.mkShell {
        name = "artiq-flashing-environment";
        buildInputs = artiq.devShell.x86_64-linux.buildInputs ++
        [
          artiq.packages.x86_64-linux.openocd-bscanspi
        ];
      };
    };

  nixConfig = {
    extra-trusted-public-keys = "nixbld.m-labs.hk-1:5aSRVA5b320xbNvu30tqxVPXpld73bhtOeH6uAjRyHc=";
    extra-substituters = "https://nixbld.m-labs.hk";
    extra-sandbox-paths = "/opt";
    bash-prompt = "\\e[1m\\e[32mICL ARTIQ \\e[0m\\e[94m(\\w)\\e[0m $ ";
  };
}
