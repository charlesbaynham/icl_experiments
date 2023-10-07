{
  inputs.pyaion.url = "git+https://gitlab.com/aion-physics/code/artiq/pyaion.git";
  inputs.nixpkgs.follows = "pyaion/nixpkgs";

  outputs = { self, nixpkgs, flake-utils, pyaion, ... }:
    flake-utils.lib.eachSystem [ "x86_64-linux" ]
      (system:
        let
          outputs = pyaion.lib.${system}.artiq_flake_builder { poetry_app = self; };
        in
        {
          inherit (outputs) packages apps formatter devShells;
        }
      );
}
