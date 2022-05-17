{
  inputs = {
    artiq.url = "git+ssh://git@gitlab.com/aion-physics/code/artiq/forks/artiq_fork.git";
    nixpkgs.follows = "artiq/nixpkgs";
  };

  outputs = { self, artiq, nixpkgs }:
    let
      pkgs = import nixpkgs { system = "x86_64-linux"; };
    in rec {
      # # Define a default app, to be run by "nix run"
      # # This launches an artiq_master + artiq_controller session
      # apps.x86_64-linux.artiq = {
      #   type = "app";
      #   program = "${nixpkgs.legacyPackages.x86_64-linux.bash}/bin/bash";
      # };
      # apps.x86_64-linux.default = apps.x86_64-linux.artiq;

      devShells.x86_64-linux.default = devShells.x86_64-linux.artiq;

      devShells.x86_64-linux.artiq = pkgs.mkShell {
        name = "icl-artiq-environment";
        buildInputs = [
          (pkgs.python3.withPackages(ps: [
            artiq.packages.x86_64-linux.artiq
            ps.numpy ps.ipython ps.jupyter ps.pip
           ]))
        ];
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
