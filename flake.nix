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

    # Oxford's ndscan ARTIQ extension + supporting package
    ndscan = {
      url = "github:OxfordIonTrapGroup/ndscan";
      flake = false;
    };
    oitg = {
      url = "github:OxfordIonTrapGroup/oitg";
      flake = false;
    };

    # My own naffly named calibration package
    qbutler = {
      url = "git+https://gitlab.com/aion-physics/code/artiq/qbutler.git";
      inputs = {
        nixpkgs.follows = "nixpkgs";
        ndscan.follows = "ndscan";
        oitg.follows = "oitg";
      };
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

    # Controller for quickly writing generic information to InfluxDB
    artiq_influx_generic = {
      url = "git+https://gitlab.com/charlesbaynham/artiq_influx_generic";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    { self
    , flake-utils
    , artiq
    , nixpkgs
    , mach-nix
    , pyaion
    , ndscan
    , oitg
    , artiq_influx_generic
    , qbutler
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

        artiq_influx_generic.packages.${system}.artiq_influx_generic
      ];
      # Packages which were built with mach-nix
      machnixPackages = [
        pyaion.defaultPackage.${system} # The shared AION package
        qbutler.defaultPackage.${system}
        ndscan # Actually just the source of a package, but mach-nix will process it
        oitg # Also just the source of a package, needed for ndscan
      ];
      # Non-python dependencies
      nonPythonDeps = [
        pkgs.concurrently # For simultaneous launching of multiple processes
        pkgs.nixpkgs-fmt # For formatting of Nix code
        pkgs.git # needed for pre-commit
        pkgs.librsvg # needed for latex docs conversion of SVGs
        pkgs.influxdb # Not used by artiq directly, but useful to have in the devshell
        pkgs.grafana # Not used by artiq directly, but useful to have in the devshell

        pkgs.qt5.full # Nasty hack to temporarily get QT working
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

      # We use mach-nix to process the python packages / requirements list into a
      # python environment which solves these constaints
      pythonEnv = mach-nix.lib.${system}.mkPython {
        requirements = pyPIRequirements + "\n" + nonPyPIRequirements;
        packagesExtra = machnixPackages;
        # Patch our non-public packages into nixpkgs before machnix runs, so
        # that they are treated the same way as public packages:
        overridesPre = [
          (final: prev: nonPyPIPackagesByName)
        ];
        # This complex looking expression is run on the output set of python
        # packages from mach-nix, after it has done its job of altering versions
        # until our set of requirements is met. This expression loops through
        # all python packages and sets "permitUserSite = true" in their
        # buildPythonPackage derivation call. This prevents nix from wrapping
        # any binaries that they produce with an "export
        # PYTHONNOUSERSITE='true'" prefix, which would disable user site
        # packages. Nix does this normally to ensure reproducability (which we
        # want), however it's added to every single binary produced. By turning
        # it off for the packages, we allow control over this variable at the
        # environment level. We use this to disable user site packages normally
        # (for reproducability), but to enable them when running in development
        # mode so that users can use pip to install packages in editable mode,
        # for quick debugging/development. See allRequirementsDebug below. TODO:
        # document this better.
        overridesPost = [
          (final: prev:
            (builtins.mapAttrs
              (
                name: pkg:
                  if (
                    builtins.isAttrs pkg &&
                    builtins.hasAttr "override" pkg &&
                    builtins.hasAttr "permitUserSite" pkg.override.__functionArgs
                  ) then
                    (pkg.override (x: { permitUserSite = true; }))
                  else
                    pkg
              )
              prev)
          )
        ];
        providers = {
          # This is a bugfix, because pythonparser IS in PyPI, but not the
          # latest version. We therefore force it to use the nixpkgs
          # version, which we've just created via overridePre. Remove once
          # https://github.com/m-labs/pythonparser/issues/31 is closed.
          pythonparser = "nixpkgs";
        };
      };

      # Finally, we build package the python environement with non-python
      # dependencies into a list that can be used as a list of buildInput
      # dependencies to reproduce our ARTIQ environment
      allRequirements = [
        pythonEnv
      ] ++ nonPythonDeps;

      # Create a copy of the same, but with the python environment set to allow use of
      # pip. If you install packages with pip they will take priority over nix ones.
      # This should only be used for debugging since it breaks the reproducability of nix.
      allRequirementsDebug = [
        (
          pythonEnv.override (prev: {
            permitUserSite = true;
          })
        )
      ] ++ nonPythonDeps;

    in
    rec
    {
      # This is the main shell, in which our artiq instance will run
      devShells.artiq = pkgs.mkShell {
        name = "icl-artiq-environment";
        buildInputs = allRequirements;
      };

      # This is the same, except that pip is enabled to install packages locally
      # (or in editable mode) for testing / developing
      devShells.artiqDev = pkgs.mkShell {
        name = "icl-artiq-environment";
        buildInputs = allRequirementsDebug;
        shellHook = ''
          # Register a local directory as a user site packages directory. Pip
          # will default to installing packages here when it discovers that it
          # can't write to the global site-packages, and python will treat this
          # site-packages as a higher priority than the global (nix) one. Note
          # that this is not a typical "venv" virtualenv, in that it does not
          # contain copies of the python binaries
          mkdir -p $(pwd)/.venv/${pkgs.python3.sitePackages}
          export PYTHONUSERBASE=$(pwd)/.venv

          # Add the binary venv path to the system search path
          export PATH="$(pwd)/.venv/bin:$PATH"

          # Give up on reproducability - we're in dev mode
          unset SOURCE_DATE_EPOCH

          # Tell pip to ignore already installed packages by default, otherwise
          # it will fail with an error because it can't uninstall them from the
          # global sitepackages
          export PIP_IGNORE_INSTALLED=true

          # Finally, another fix. Nix's python environment uses a
          # "sitecustomize.py" file to parse NIX_... environmental variables
          # into python environments. However, this file ends up changing
          # sys.prefix so that it's no longer equal to sys.base_prefix,
          # resulting in python thinking it's in a virtual environment even
          # though it isn't (the nix python installation is a system
          # installation, not a venv). I think this is a bug, (see
          # https://github.com/NixOS/nixpkgs/issues/201037) but I can patch it
          # like so:
          echo "import sys" > $(pwd)/.venv/${pkgs.python3.sitePackages}/usercustomize.py
          echo "sys.base_prefix = sys.prefix" >> $(pwd)/.venv/${pkgs.python3.sitePackages}/usercustomize.py

          echo "*** WARNING: Entering development mode ***"
          echo "Packages installed by pip are not tracked by Nix so ARTIQ experiments run in this mode are not reproducable"
        '';
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
            sphinx-apidoc -o docs/autogen/repo repository
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
            sphinx-apidoc -o docs/autogen/repo repository
            sphinx-build docs latex -b latex
            mv latex $out
          '';
        };
      };


      apps = {
        docs =
          let
            script = pkgs.writeShellScriptBin "launch_server" ''
              export PATH=${pkgs.lib.makeBinPath allRequirements}:$PATH

              exec sphinx-autobuild docs html_out --pre-build 'sphinx-apidoc -o docs/autogen/repo "repository"' --watch repository
            '';
          in
          { type = "app"; program = "${script}/bin/launch_server"; };

        update_requirements =
          let
            script = pkgs.writeShellScriptBin "update_requirements" ''
              export PATH=${pkgs.lib.makeBinPath allRequirements}:$PATH

              pip-compile requirements.in
            '';
          in
          { type = "app"; program = "${script}/bin/update_requirements"; };

        pytest =
          let
            script = pkgs.writeShellScriptBin "pytest" ''
              export PATH=${pkgs.lib.makeBinPath allRequirements}:$PATH

              coverage run --omit "tests/*,*/_version.py,/nix/store/*" -m pytest --junitxml=report.xml $1
              test_exit_code=$?
              coverage report
              exit "$test_exit_code"
            '';
          in
          { type = "app"; program = "${script}/bin/pytest"; };

        run_artiq =
          let
            script = pkgs.writeShellScriptBin "run_artiq" ''
              export PATH=${pkgs.lib.makeBinPath allRequirements}:$PATH

              exec ./scripts/launch_script.sh "$@"
            '';
          in
          { type = "app"; program = "${script}/bin/run_artiq"; };

        dashboard =
          let
            script = pkgs.writeShellScriptBin "run_artiq" ''
              export PATH=${pkgs.lib.makeBinPath allRequirements}:$PATH

              exec artiq_dashboard -v -p ndscan.dashboard_plugin "$@"
            '';
          in
          { type = "app"; program = "${script}/bin/run_artiq"; };

        backup_datasets =
          let
            script = pkgs.writeShellScriptBin "run" ''
              export PATH=${pkgs.lib.makeBinPath [pkgs.rsync]}:$PATH

              # Unlike the other scripts, this one is launched w.r.t. the working directory
              # so that if the working dir isn't correct, it'll fail with an error message
              # rather than looking like it's working and then not actuall backing up the data.
              exec ./scripts/backup_datasets.sh
            '';
          in
          { type = "app"; program = "${script}/bin/run"; };

        backup_database =
          let
            script = pkgs.writeShellScriptBin "run" ''
              export PATH=${pkgs.lib.makeBinPath [pkgs.influxdb]}:$PATH

              exec ${self}/scripts/backup_database.sh
            '';
          in
          { type = "app"; program = "${script}/bin/run"; };

        database =
          let
            script = pkgs.writeShellScriptBin "run" ''
              export PATH=${pkgs.lib.makeBinPath [pkgs.influxdb]}:$PATH

              exec ${self}/scripts/launch_database.sh
            '';
          in
          { type = "app"; program = "${script}/bin/run"; };

        grafana =
          let
            provisioning_dir = "${self}/scripts/grafana_provisioning";
            script = pkgs.writeShellScriptBin "run" ''
              export PATH=${pkgs.lib.makeBinPath [pkgs.grafana]}:$PATH
              export GRAFANA_HOMEPATH=${pkgs.grafana}/share/grafana
              export GF_PATHS_PROVISIONING=${provisioning_dir}

              exec ${self}/scripts/launch_grafana.sh
            '';
          in
          { type = "app"; program = "${script}/bin/run"; };
      };
    }
    );

  nixConfig = {
    bash-prompt = "\\[\\e[1m\\e[32m\\]ICL ARTIQ \\[\\e[0m\\e[94m\\](\\w)\\[\\e[0m\\] $ ";
  };

}
