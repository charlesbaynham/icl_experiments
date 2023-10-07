{
  inputs.pyaion.url = "git+file:///home/charles/pyaion";
  inputs.nixpkgs.follows = "pyaion/nixpkgs";

  outputs = { self, nixpkgs, flake-utils, pyaion, ... }:
    flake-utils.lib.eachSystem [ "x86_64-linux" ]
      (system:
        let
          originalOutputs = pyaion.lib.${system}.artiq_flake_builder { poetry_app = self; };
          overriddenOutputs = originalOutputs.override (prev: {
            extra-build-requirements = {
              artiq-http = [ "setuptools" ];
              koheron-ctl200-laser-driver = [ "setuptools" ];
              qbutler = [ "setuptools" ];
              wand = [ "setuptools" ]; # FIXME: probably needs some QT wrapping
            };
          });

        in
        {
          inherit (overriddenOutputs) packages apps formatter devShells;
        }
      );
}
