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

  # Set GI_TYPELIB_PATH to point to the aravis libraries
  GI_TYPELIB_PATH = "${pkgs.aravis.lib}/lib/girepository-1.0/";

  # Override make_deb.py so that it doesn't try to call git
  preBuild = ''
    echo "import aravis" > make_deb.py
    echo "DEBVERSION=aravis.__version__" >> make_deb.py
    echo GI_TYPELIB_PATH=$GI_TYPELIB_PATH
  '';

  # Add a hook to dependent packages so that aravis is added to their GI_TYPELIB_PATH too
  setupHook = pkgs.writeShellScript "hook.sh" ''
    export GI_TYPELIB_PATH=''${GI_TYPELIB_PATH:+$GI_TYPELIB_PATH:}${GI_TYPELIB_PATH}
    echo Adding aravis to GI_TYPELIB_PATH
  '';
}
