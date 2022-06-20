{
  inputs = {
    # Use a consistant version of nixpkgs for all dependencies.
    #
    # Until https://github.com/NixOS/nix/pull/6550 is merged, we have to specify
    # a "follows" for each subsequent package
    #
    # Mach-nix is the pickest package we have when it comes to nixpkgs, so we'll
    # use its version.
    nixpkgs.follows = "mach-nix/nixpkgs";

    # Useful utilities for flake packaging
    flake-utils.url = "github:numtide/flake-utils";

    artiq = {
      url = "git+https://gitlab.com/aion-physics/code/artiq/forks/artiq_fork.git";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # Mach-nix is an extension to nix which allows you to build python
    # environments reproducably while still fetching packages from nixpkgs and
    # having fully-fledged dependency resolution.
    mach-nix = {
      url = "mach-nix";

      # The "pypi-deps-db" is the static description of the latest packages
      # available on PyPI. Because of how flakes work, if we want an up-to-date
      # version of this (which we do) we need to specify it manually, otherwise
      # we'll get the version that was locked most recently in mach-nix.
      inputs.pypi-deps-db.follows = "pypi-deps-db";
    };

    # See above
    pypi-deps-db = {
      url = "github:DavHau/pypi-deps-db";
      flake = false;
    };

    # Our shared PyAION package
    pyaion = {
      url = "git+https://gitlab.com/aion-physics/code/artiq/pyaion.git";
      inputs.mach-nix.follows = "mach-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # Our internal ICL_AION package
    icl_aion = {
      url = "git+https://gitlab.com/aion-physics/code/artiq/device-packages/icl_aion.git";
      inputs.mach-nix.follows = "mach-nix";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.pyaion.follows = "pyaion";
    };
  };

  outputs =
    { self
    , flake-utils
    , artiq
    , nixpkgs
    , mach-nix
    , pyaion
    , icl_aion
    , ...
    }:
    flake-utils.lib.eachDefaultSystem (system:
    let
      pkgs = nixpkgs.legacyPackages.${system};

      # ARTIQ has a version number which is not semver compliant, so cannot be
      # parsed by mach-nix. Since we know exactly what version of ARTIQ we want,
      # there's no change of mach-nix accidentally choosing the wrong version.
      # We therefore override the version number to anything we want, as long as
      # it's semver compliant. This won't affect what artiq thinks its version
      # number is: it's only used for the mach-nix selection process.
      patched_artiq = artiq.packages.${system}.artiq // { "version" = "0.0.0"; };

      ### Requirements ###
      # Define the requirements for the ARTIQ environment. These are used to
      # launch a devShell with these requirements present.

      # Packages built with buildPythonPackage but which are not in nixpkgs already
      nonPyPIPackages = [
        patched_artiq

        artiq.packages.${system}.llvmlite-new
        artiq.packages.${system}.pythonparser
        artiq.packages.${system}.qasync
        artiq.inputs.sipyco.packages.${system}.sipyco
        artiq.inputs.artiq-comtools.packages.${system}.artiq-comtools
      ];
      # Packages which were built with mach-nix
      machnixPackages = [
        icl_aion.packages.${system}.icl_aion # Our supporting, system-specific package
        pyaion.defaultPackage.${system} # The shared AION package
      ];
      # Non-python dependencies
      nonPythonDeps = [
        pkgs.concurrently # For simultaneous launching of multiple processes
        pkgs.nixpkgs-fmt # For formatting of Nix code
        pkgs.git # needed for pre-commit
        pkgs.librsvg # needed for latex docs conversion of SVGs
      ];
      # The rest: a newline-seperated string, listing PyPI dependencies (like a
      # normal python package). These are read from the file "requirements.in",
      # so you should edit them there. That way, this package can also be
      # installed via pip. To keep the nix environment and the requirements.txt
      # lock file in sync, run (TODO: add lock file synccer)
      pyPIRequirements = builtins.readFile ./requirements.in;

      ### End requirements ###

      # Here we define a function which patches all the ARTIQ packages (or
      # rather, packages built with nixpkgs.buildPythonPackage but which are not
      # in nixpkgs) into nixpkgs. This allows mach-nix to see them so that it
      # can choose to update them if required. If we don't do this, and if these
      # packages share dependencies with others which *are* parsed by mach-nix,
      # we'll end up with collisions in our python environment. Note: we must
      # also explicitly tell mach-nix that these are dependencies, otherwise it
      # also won't work for esoteric reasons. Ask me how I know.
      nonPyPIPackagesByName =
        builtins.listToAttrs (
          map (newpkg: ({ name = newpkg.pname; value = newpkg; })) nonPyPIPackages
        );
      # We also compile a list of their names, for adding into requirements
      nonPyPIRequirements = pkgs.lib.concatStringsSep "\n" (map (p: p.pname) nonPyPIPackages);

      # For the documentation:
      fullVersion = "${self.shortRev or "dirty-${self.lastModifiedDate}"}";

      # Finally, we build all of the above into a list of requirements that the
      # environment will have
      allRequirements = [
        (
          mach-nix.lib.${system}.mkPython {
            requirements = pyPIRequirements + "\n" + nonPyPIRequirements;
            packagesExtra = machnixPackages;
            overridesPre = [
              (final: prev: nonPyPIPackagesByName)
            ];
            providers = {
              # This is a bugfix, because pythonparser IS in PyPI, but not the
              # latest version. We therefore force it to use the nixpkgs
              # version, which we've just created via overridePre. Remove once
              # https://github.com/m-labs/pythonparser/issues/31 is closed.
              pythonparser = "nixpkgs";
            };
          }
        )
      ] ++ nonPythonDeps;

    in
    rec
    {
      inherit allRequirements;

      # This is the main shell, in which our artiq instance will run
      devShells.artiq = pkgs.mkShell {
        name = "icl-artiq-environment";
        buildInputs = allRequirements;
      };

      # An environment with the tools required for flashing gateware loaded.
      devShells.flash = pkgs.mkShell {
        name = "artiq-flashing-environment";
        buildInputs = artiq.devShell.${system}.buildInputs ++
          [
            artiq.packages.${system}.openocd-bscanspi
          ];
      };

      # Set default devShell to the ARTIQ environment
      devShells.default = devShells.artiq;

      # Specify a formatter for consistant formatting, via `nix fmt`
      formatter = nixpkgs.legacyPackages.${system}.nixpkgs-fmt;

      # Build the documentation as outputs
      packages = {
        docs_html = pkgs.stdenv.mkDerivation {
          pname = "icl_experiments_docs_html";
          version = fullVersion;
          src = self;
          phases = [ "buildPhase" ];
          buildInputs = allRequirements;
          SPHINX_APIDOC_OPTIONS = "members,show-inheritance";
          GIT_DESCRIBE = fullVersion; # Override for sphinx's versioning
          buildPhase = ''
            cp -r $src/* .
            chmod -R +w .
            sphinx-apidoc -o docs/autogen repository
            sphinx-build docs html_out -b html
            mv html_out $out
          '';
        };

        docs_latex = pkgs.stdenv.mkDerivation {
          pname = "icl_experiments_docs_latex";
          version = fullVersion;
          src = self;
          phases = [ "buildPhase" ];
          buildInputs = allRequirements;
          SPHINX_APIDOC_OPTIONS = "members,show-inheritance";
          GIT_DESCRIBE = fullVersion; # Override for sphinx's versioning
          buildPhase = ''
            cp -r $src/* .
            chmod -R +w .
            sphinx-apidoc -o docs/autogen repository
            sphinx-build docs latex -b latex
            mv latex $out
          '';
        };
      };

      apps.docs =
        let
          script = pkgs.writeShellScriptBin "launch_server" ''
            export PATH=${pkgs.lib.makeBinPath allRequirements}:$PATH

            sphinx-apidoc -o docs/autogen repository
            exec sphinx-autobuild docs html_out
          '';
        in
        { type = "app"; program = "${script}/bin/launch_server"; };

      apps.update_requirements =
        let
          script = pkgs.writeShellScriptBin "update_requirements" ''
            export PATH=${pkgs.lib.makeBinPath allRequirements}:$PATH

            pip-compile requirements.in
          '';
        in
        { type = "app"; program = "${script}/bin/update_requirements"; };

      apps.pytest =
        let
          script = pkgs.writeShellScriptBin "pytest" ''
            export PATH=${pkgs.lib.makeBinPath allRequirements}:$PATH

            coverage run --omit "tests/*,*/_version.py,/nix/store/*" -m pytest --junitxml=report.xml $1
            coverage report
          '';
        in
        { type = "app"; program = "${script}/bin/pytest"; };
      
      apps.run_artiq =
        let
          script = pkgs.writeShellScriptBin "run_artiq" ''
            export PATH=${pkgs.lib.makeBinPath allRequirements}:$PATH

            exec ./scripts/launch_script.sh "$@"
          '';
        in
        { type = "app"; program = "${script}/bin/run_artiq"; };
    }
    );

  nixConfig = {
    extra-trusted-public-keys = "nixbld.m-labs.hk-1:5aSRVA5b320xbNvu30tqxVPXpld73bhtOeH6uAjRyHc=";
    extra-substituters = "https://nixbld.m-labs.hk";
    bash-prompt = "\\[\\e[1m\\e[32m\\]ICL ARTIQ \\[\\e[0m\\e[94m\\](\\w)\\[\\e[0m\\] $ ";
  };

}
