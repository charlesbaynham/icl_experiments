{
  inputs = {
    nixpkgs.follows = "artiq/nixpkgs";

    artiq.url = "git+https://gitlab.com/aion-physics/code/artiq/forks/artiq_fork.git";

    mach-nix.url = "mach-nix";
    mach-nix.inputs.nixpkgs.follows = "nixpkgs";
    mach-nix.inputs.pypi-deps-db.follows = "pypi-deps-db";

    pypi-deps-db = {
      url = "github:DavHau/pypi-deps-db";
      flake = false;
    };

    icl_aion.url = "git+https://gitlab.com/aion-physics/code/artiq/device-packages/icl_aion.git";
    icl_aion.inputs.pyaion.follows = "pyaion";
    icl_aion.inputs.nixpkgs.follows = "nixpkgs";
    icl_aion.inputs.mach-nix.follows = "mach-nix";

    pyaion.url = "git+https://gitlab.com/aion-physics/code/artiq/pyaion.git";
    pyaion.inputs.nixpkgs.follows = "nixpkgs";
    pyaion.inputs.mach-nix.follows = "mach-nix";
  };

  outputs =
    { self
      , artiq
    , nixpkgs
    , mach-nix
    , pypi-deps-db
    , icl_aion
    , pyaion
    }:
    let
      artiq_overlay = self: super:
        {
          python3 = super.python3.override {
            packageOverrides = self: super: {
              artiq = artiq.packages.x86_64-linux.artiq;
            };
          };
          python3Packages = self.python3.pkgs;

          artiq = artiq.packages.x86_64-linux.artiq;
        };
      artiq_override = self: super: {
              artiq = artiq.packages.x86_64-linux.artiq;
            };

      pkgs = import nixpkgs { system = "x86_64-linux"; overlays = [ artiq_overlay ]; };

      mach-nix-lib = (import mach-nix {
            inherit pkgs;
            dataOutdated = false;
            pypiData = pypi-deps-db;
            python = "python3";
      });

      # Define the requirements for the ARTIQ environment.
      # These are used to launch a devShell with these requirements present
      # (launched with `nix develop`) which can then be used to launch an ARTIQ instance.
      # Alternatively, run the shell script "run_artiq.sh" to launch an artiq_master + artiq_ctlmgr session
      nonPyPIPackages = [
          # artiq.packages.x86_64-linux.artiq # The main ARTIQ package
      ];
      machnixPackages = [
          icl_aion.packages.x86_64-linux.icl_aion # Our supporting, system-specific package
          pyaion.defaultPackage.x86_64-linux # The shared AION package
        ];
      nonPythonDeps = [
        pkgs.concurrently # For simultaneous launching of multiple processes
        pkgs.nixpkgs-fmt # For formatting of Nix code
      ];

      # requirements = [
      #   (pkgs.python3.withPackages (ps: [
      #     artiq.packages.x86_64-linux.artiq # The main ARTIQ package
      #     icl_aion.packages.x86_64-linux.icl_aion # Our supporting, system-specific package
      #     pyaion.defaultPackage.x86_64-linux # The shared AION package
          # ps.numpy
          # ps.ipython
          # ps.jupyter
          # ps.black # Code formatting within the IDE - pre-commit is the authority on which code style is enforced however
          # ps.pip # For debugging
      #   ]))

      # ];

    in
    rec {
      inherit pkgs mach-nix-lib;

      # Define a devshell with the ARTIQ dependancies available.
      # This is the environment used for running the ARTIQ session.
      # devShells.x86_64-linux.artiq = pkgs.mkShell {
        # name = "icl-artiq-environment";
        # buildInputs = requirements;
      # };

      devShells.x86_64-linux.artiq = pkgs.mkShell {
        name = "icl-artiq-environment";
        buildInputs = [
          (mach-nix-lib.mkPython {
            requirements = builtins.readFile ./requirements.in + ''
              artiq
            '';
            packagesExtra = machnixPackages;
            overridesPre = [(
             pySelf: pySuper: {
               artiq = artiq.packages.x86_64-linux.artiq;
             }
            )];
            providers = {
              artiq = "nixpkgs";
            };
          })
        ];# ++ nonPythonDeps;
      };

      # An environment with the tools required for flashing gateware loaded.
      devShells.x86_64-linux.flash = pkgs.mkShell {
        name = "artiq-flashing-environment";
        buildInputs = artiq.devShell.x86_64-linux.buildInputs ++
          [
            artiq.packages.x86_64-linux.openocd-bscanspi
          ];
      };

      # Set default devShell to the ARTIQ environment
      devShells.x86_64-linux.default = devShells.x86_64-linux.artiq;

      # Specify a formatter for consistant formatting, via `nix fmt`
      formatter.x86_64-linux = nixpkgs.legacyPackages.x86_64-linux.nixpkgs-fmt;
    };

  nixConfig = {
    extra-trusted-public-keys = "nixbld.m-labs.hk-1:5aSRVA5b320xbNvu30tqxVPXpld73bhtOeH6uAjRyHc=";
    extra-substituters = "https://nixbld.m-labs.hk";
    extra-sandbox-paths = "/opt";
    bash-prompt = "\\[\\e[1m\\e[32m\\]ICL ARTIQ \\[\\e[0m\\e[94m\\](\\w)\\[\\e[0m\\] $ ";
  };
}
