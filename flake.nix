{
  inputs = {
    artiq.url = "git+https://gitlab.com/aion-physics/code/artiq/forks/artiq_fork.git";
    nixpkgs.follows = "artiq/nixpkgs";
  };

  outputs = { self, artiq, nixpkgs }:
    let
      pkgs = import nixpkgs { system = "x86_64-linux"; };

      # Define the requirements for the ARTIQ environment.
      # These are used to launch a devShell with these requirements present
      # (launched with `nix develop`) which can then be used to launch an ARTIQ instance.
      # Alternatively, run the shell script "run_artiq.sh" to launch an artiq_master + artiq_ctlmgr session
      requirements = [
        (pkgs.python3.withPackages (ps: [
          artiq.packages.x86_64-linux.artiq # The main ARTIQ package
          ps.numpy
          ps.ipython
          ps.jupyter
          ps.pre-commit # Code formatting on commits. More extensive / repeatable than just running black
          ps.black # Code formatting within the IDE - pre-commit is the authority on which code style is enforced however
        ]))
        pkgs.concurrently # For simultaneous launching of multiple processes
        pkgs.nixpkgs-fmt # For formatting of Nix code
      ];

    in
    rec {
      # Define a devshell with the ARTIQ dependancies available.
      # This is the environment used for running the ARTIQ session.
      devShells.x86_64-linux.artiq = pkgs.mkShell {
        name = "icl-artiq-environment";
        buildInputs = requirements;
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
    bash-prompt = "\\e[1m\\e[32mICL ARTIQ \\e[0m\\e[94m(\\w)\\e[0m $ ";
  };
}
