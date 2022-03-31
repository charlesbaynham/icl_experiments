{
  inputs.artiq.url = "git+ssh://git@gitlab.com/aion-physics/code/artiq/forks/artiq_fork.git";
  inputs.nixpkgs.follows = "artiq/nixpkgs";

  outputs = { self, artiq, nixpkgs }:
    let
      pkgs = import nixpkgs { system = "x86_64-linux"; };
    in {
      devShell.x86_64-linux = pkgs.mkShell {
        name = "icl-artiq-environment";
        buildInputs = [
          (pkgs.python3.withPackages(ps: [
            artiq.packages.x86_64-linux.artiq 
            ps.numpy ps.ipython ps.jupyter ps.pip
           ]))
        ];
      };
    };
}
