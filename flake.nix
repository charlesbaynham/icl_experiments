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

      patched_artiq = artiq.packages.x86_64-linux.artiq  // { "version" = "1.2.3"; };

      artiq_override = self: super: {
        # artiq = artiq.packages.x86_64-linux.artiq;
        artiq = patched_artiq;
      };

      mnix = mach-nix.lib.x86_64-linux.mkPython {
            requirements = ''
              numpy  # (for example - I actually need more)
              pip
              artiq > 1.0
            '';
            packagesExtra = [
              pyaion.packages.x86_64-linux.pyaion
            ];
            overridesPre = [ artiq_override ];
            providers = {
              artiq = "nixpkgs";
            };
          };

    in
    rec {
      inherit pkgs mnix patched_artiq;

      mnixPkgs  = mach-nix.lib.x86_64-linux.mkNixpkgs  {
            requirements = ''
              numpy  # (for example - I actually need more)
              pip
              artiq > 1.0
            '';
            packagesExtra = [
              pyaion.packages.x86_64-linux.pyaion
            ];
            overridesPre = [ artiq_override ];
            providers = {
              artiq = "nixpkgs";
            };
          };

      devShells.x86_64-linux.default = pkgs.mkShell {
        name = "icl-artiq-environment";
        buildInputs = [
          (mnix)
        ];
      };
    };
}
