{ pkgs ? import <nixpkgs> { } }:
pkgs.python3Packages.buildPythonPackage rec {
  pname = "python-aravis";
  version = "0.5";
  src = pkgs.fetchFromGitHub {
    owner = "SintefManufacturing";
    repo = "python-aravis";
    rev = "5750250cedb9b96d7a0172c0da9c1811b6b817af";
    sha256 = "sha256-PQfi9ehGHJMFkMj9Wp0D9u2/iaqOz44B39/dpYJJPCs=";
  };
  propagatedBuildInputs = with pkgs.python3Packages; [
    numpy
    pygobject3

    pkgs.aravis
  ];

  patches = [
    (pkgs.substituteAll {
      aravisPath = pkgs.aravis;
      src = ./nix/aravis/patch_to_only_import_once.diff;
    })
  ];

  preBuild = ''
    # Override make_deb.py so that it doesn't try to call git
    echo "import aravis" > make_deb.py
    echo "DEBVERSION=aravis.__version__" >> make_deb.py

    # # Override aravis.py to bake in the GI_TYPELIB_PATH variable
    # touch tmp
    # echo ### patches by nix ### >> tmp
    # echo 'import os' >> tmp
    # echo 'os.environ["GI_TYPELIB_PATH"] = "${pkgs.aravis.lib}/lib/girepository-1.0/"' >> tmp
    # echo ### end patches by nix ### >> tmp

    # cat tmp aravis.py > tmp2
    # mv tmp2 aravis.py
    # rm tmp
  '';
}
