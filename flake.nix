{
  description = "Regenerate this branch's experiment stubs from one or more source branches.";

  # Pinned to the exact nixpkgs revision the master branch's flake resolves to
  # (master's `nixpkgs` input follows pyaion's `nixpkgs`, currently this same
  # nixos-23.05 commit), so `git` and `python3` here match master's build
  # environment. Update by hand alongside master's pin, not with `nix flake
  # update` (there is nothing else here to accidentally drift).
  inputs.nixpkgs.url = "git+https://github.com/NixOS/nixpkgs.git?rev=8a4c17493e5c39769f79117937c79e1c88de6729&shallow=1";

  outputs = {
    self,
    nixpkgs,
  }: let
    system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};

    # scripts/generate_stubs.py only needs Python's stdlib plus git (to read
    # the source branches without checking them out).
    script = pkgs.writeShellScriptBin "run" ''
      export PATH=${pkgs.lib.makeBinPath [pkgs.git pkgs.python3]}:$PATH
      exec python3 ${self}/scripts/generate_stubs.py "$@"
    '';
  in {
    apps.${system} = {
      generate_stubs = {
        type = "app";
        program = "${script}/bin/run";
      };
      default = self.apps.${system}.generate_stubs;
    };
  };
}
