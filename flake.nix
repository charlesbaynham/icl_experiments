{
  description = "Regenerate this branch's experiment stubs from one or more source branches.";

  # Pinned to the exact nixpkgs revision the master branch's flake resolves to
  # (master's `nixpkgs` input follows pyaion's `nixpkgs`, currently this same
  # nixos-23.05 commit), so `git` and `python3` here match master's build
  # environment. Update by hand alongside master's pin, not with `nix flake
  # update` (there is nothing else here to accidentally drift).
  inputs.nixpkgs.url = "git+https://github.com/NixOS/nixpkgs.git?rev=8a4c17493e5c39769f79117937c79e1c88de6729&shallow=1";

  # Pre-commit / git-hooks, mirroring master. This branch shares its .git
  # directory with the real repo, so the pre-commit hook installed while on
  # master (git hooks live in .git/hooks and survive branch switches) is still
  # present after checking out this branch. Without the machinery below it
  # points at a config that no longer exists here and blocks every commit, so we
  # reinstate the same hooks the master flake defines.
  inputs.git-hooks.url = "github:cachix/git-hooks.nix";

  outputs = {
    self,
    nixpkgs,
    git-hooks,
  }: let
    system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};

    # scripts/generate_stubs.py only needs Python's stdlib plus git (to read
    # the source branches without checking them out).
    script = pkgs.writeShellScriptBin "run" ''
      export PATH=${pkgs.lib.makeBinPath [pkgs.git pkgs.python3]}:$PATH
      exec python3 ${self}/scripts/generate_stubs.py "$@"
    '';

    # Pre-commit hooks and the self-healing installer live in
    # ./nix/precommit.nix, copied verbatim from master.
    precommit = import ./nix/precommit.nix {
      inherit pkgs;
      patchedPreCommit = git-hooks.packages.${system}.pre-commit;
      preCommitCheck = self.checks.${system}.pre-commit-check;
    };
  in {
    apps.${system} = {
      generate_stubs = {
        type = "app";
        program = "${script}/bin/run";
      };
      default = self.apps.${system}.generate_stubs;
    };

    # `nix develop` installs the pre-commit git hook via precommit.shellHook.
    devShells.${system}.default = pkgs.mkShell {
      shellHook = precommit.shellHook;
    };

    checks.${system} = {
      # Pre-commit formatting, copied from master's flake. see
      # https://devenv.sh/reference/options/#pre-commithooks for a list of
      # options
      pre-commit-check = git-hooks.lib.${system}.run {
        src = ./.;
        hooks = {
          alejandra.enable = true;
          autoflake.enable = true;
          autoflake.args = [
            "--remove-all-unused-imports"
            "--remove-unused-variables"
            "--in-place"
          ];
          black.enable = true;
          check-case-conflicts.enable = true;
          check-merge-conflicts.enable = true;
          check-yaml.enable = true;
          end-of-file-fixer.enable = true;
          isort.enable = true;
          isort.args = ["--profile" "black" "--force-single-line-imports"];
          mixed-line-endings.enable = true;
          prettier.enable = true;
          taplo.enable = true;
          trim-trailing-whitespace.enable = true;
        };
      };
    };
  };
}
