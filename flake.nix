{
  inputs = {
    artiq.url = "git+ssh://git@gitlab.com/aion-physics/code/artiq/forks/artiq_fork.git";
    nixpkgs.follows = "artiq/nixpkgs";
  };

  outputs = { self, artiq, nixpkgs }:
    let
      pkgs = import nixpkgs { system = "x86_64-linux"; };
    in rec {
      devShell.x86_64-linux = pkgs.mkShell {
        name = "icl-artiq-environment";
        buildInputs = [
          (pkgs.python3.withPackages(ps: [
            artiq.packages.x86_64-linux.artiq
            ps.numpy ps.ipython ps.jupyter ps.pip
           ]))
        ];
      };

      devShells.x86_64-linux.flash = pkgs.mkShell {
        name = "artiq-environment";
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
  };
}
