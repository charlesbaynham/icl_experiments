{
  inputs = {
    nixpkgs.follows = "artiq/nixpkgs";
    artiq.url = "github:m-labs/artiq";
    mach-nix.url = "mach-nix";

    pyaion.url = "git+https://gitlab.com/aion-physics/code/artiq/pyaion.git";
  };

  outputs =
    { self
      , artiq
      , nixpkgs
      , mach-nix
      , pyaion
    }:
    let
      pkgs = import nixpkgs { system = "x86_64-linux"; };

      artiq_override = self: super: {
        artiq = artiq.packages.x86_64-linux.artiq;
      };

    in
    rec {
      inherit pkgs;

      devShells.x86_64-linux.default = pkgs.mkShell {
        name = "icl-artiq-environment";
        buildInputs = [
          (mach-nix.lib.x86_64-linux.mkPython {
            requirements = ''
              numpy  # (for example - I actually need more)
              pip
              # artiq
            '';
            packagesExtra = [
              pyaion.packages.x86_64-linux.pyaion
            ];
            overridesPre = [ artiq_override ];
            providers = {
              artiq = "nixpkgs";
            };
          })
        ];
      };
    };
}
