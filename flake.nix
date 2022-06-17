{
  inputs = {
    nixpkgs.follows = "artiq/nixpkgs";

    artiq.url = "git+https://gitlab.com/aion-physics/code/artiq/forks/artiq_fork.git";
  };

  outputs =
    { self
      , artiq
      , nixpkgs
      , ...
    }:
    let
      pkgs = artiq.inputs.nixpkgs.legacyPackages.x86_64-linux;
      aqmain = artiq.packages.x86_64-linux;

    in {
      artiq = aqmain.artiq;

      defaultPackage.x86_64-linux = pkgs.buildEnv {
        name = "artiq-env";
        paths = [
          # ========================================
          # EDIT BELOW
          # ========================================
          (pkgs.python3.withPackages(ps: [
            # List desired Python packages here.
            aqmain.artiq
            #ps.paramiko  # needed if and only if flashing boards remotely (artiq_flash -H)
            #aqextra.flake8-artiq

            # The NixOS package collection contains many other packages that you may find
            # interesting. Here are some examples:
            #ps.pandas
            #ps.numpy
            #ps.scipy
            #ps.numba
            #ps.matplotlib
            # or if you need Qt (will recompile):
            #(ps.matplotlib.override { enableQt = true; })
            #ps.bokeh
            #ps.cirq
            #ps.qiskit
          ]))
          #aqextra.korad_ka3005p
          #aqextra.novatech409b
          # List desired non-Python packages here
          #aqmain.openocd-bscanspi  # needed if and only if flashing boards
          # Other potentially interesting packages from the NixOS package collection:
          #pkgs.gtkwave
          #pkgs.spyder
          #pkgs.R
          #pkgs.julia
          # ========================================
          # EDIT ABOVE
          # ========================================
        ];
      };
    };
}
