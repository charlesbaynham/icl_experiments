{
  inputs = {
    nixpkgs.follows = "artiq/nixpkgs";

    artiq.url = "github:m-labs/artiq";

    mach-nix = {
      url = "mach-nix";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.pypi-deps-db.follows = "pypi-deps-db";
    };

    pypi-deps-db = {
      url = "github:DavHau/pypi-deps-db";
      flake = false;
    };

    pyaion = {
      url = "git+https://gitlab.com/aion-physics/code/artiq/pyaion.git";
    };
  };

  outputs =
    { self
      , artiq
      , nixpkgs
      , mach-nix
      , pyaion
      , ...
    }:
    let
      pkgs = import nixpkgs { system = "x86_64-linux"; };

      patched_artiq = artiq.packages.x86_64-linux.artiq  // { "version" = "1.2.3"; };

      artiq_override = self: super: {
        # artiq = artiq.packages.x86_64-linux.artiq;
        artiq = patched_artiq;
      };

      pythonparser_override = self: super: {
        pythonparser = artiq.packages.x86_64-linux.pythonparser;
      };

      mnix = mach-nix.lib.x86_64-linux.mkPython {
            requirements = ''
              numpy  # (for example - I actually need more)
              pip
              # artiq > 1.0
              pythonparser
            '';
            packagesExtra = [
              pyaion.packages.x86_64-linux.pyaion
            ];
            overridesPre = [ artiq_override pythonparser_override ];
            providers = {
              artiq = "nixpkgs";
            };
          };

    in
    rec {
      inherit pkgs mnix patched_artiq;

      # mnixPkgs  = mach-nix.lib.x86_64-linux.mkNixpkgs  {
      #       requirements = ''
      #         numpy  # (for example - I actually need more)
      #         pip
      #         artiq > 1.0
      #         pythonparser
      #       '';
      #       packagesExtra = [
      #         pyaion.packages.x86_64-linux.pyaion
      #       ];
      #       overridesPre = [ artiq_override pythonparser_override ];
      #       providers = {
      #         artiq = "nixpkgs";
      #       };
      #     };

      devShells.x86_64-linux.default = pkgs.mkShell {
        name = "icl-artiq-environment";
        buildInputs = [
          (mnix)
        ];
      };
    };
}
