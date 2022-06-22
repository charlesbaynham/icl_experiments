Readme
######

**The Imperial ARTIQ experiments repository.**

This repository holds the ARTIQ experiments, imported by ARTIQ as an
"experiment repository" and whose hash is embedded into datasets. This
also includes a complete Nix definition of the working environment
required to run ARTIQ, thus pinning all dependencies as well. The one
remaining item of information that's not recorded is the bitstream
version running on the Sinara core. It's t.b.d. how we manage this.
(TODO)

Overview
========

This repository contains the Imperial ARTIQ experiments, and also defines the
software environment in which the Imperial ARTIQ system runs. It is a nix flake:
to launch ARTIQ, see the :ref:`Launching ARTIQ` section below. This repository has an
opinionated structure and provides the following features, in approximately
descending order of importance:

#. This is one of several repositories that make up the complete Imperial ARTIQ
   installation. For the complete structure, see `the PyAION documentation
   <https://aion-physics.gitlab.io/code/artiq/pyaion/>`__.

#. This is a nix flake. That means that the build environment is fully
   defined, including versions of both python and system packages.
   Updates / additions are explicit and are recorded in the git history,
   a hash of which in included in the metadata of every dataset taken.
   For more information on how to add / update packages in your
   installation, see the Managing packages section below.

#. Definition of the ARTIQ + peripherals hardware happens elsewhere, in
   the institute-specific python packages. See `the PyAION
   documentation <https://aion-physics.gitlab.io/code/artiq/pyaion/>`__
   for details.

#. This repository uses mach-nix to handle python dependencies. Compared to
   plain nix, this give us dependency resolution, the ability to specify version
   constraints and the option to use newer / older versions of packages than
   would otherwise be available in nixpkgs.

#. The above decision can result in long (~30 minute) build times the first time
   a build is run. The CI pipeline therefore builds environments automatically
   and uploads them to a binary cache on cachix. See the :ref:`Setup` section
   for details on how to enable this, to avoid having to do lengthy builds
   locally.

#. Code in this repository can be automatically styled using pre-commit
   by running ``pre-commit run --all``. Alternatively, use
   ``pre-commit install`` to enable automatic formatting on every
   commit. These style rules will be checked automatically by the CI.

#. This repository supports direnv, and uses its Nix / flake
   integration. This means that (if desired) you can automatically enter
   the ARTIQ environment every time you ``cd`` into this folder, or open
   Visual Studio Code in it (install the direnv extension). See
   https://direnv.net/ for details.

#. Documentation for this repository is build using Sphinx. It is also
   auto-generated from Experiment files, so write your docstrings in the
   Google format.

#. Unit tests are enabled and highly recommended. Testing code that
   interacts with the ARTIQ kernel is still nigh-on impossible (though
   speak to Riverlane if you're interested in their early-access
   realtime simulator), but testing other utility functions is done via
   ``pytest``.

#. Linting checks, documentation building and unit tests will be run
   automatically using Gitlab CI.

#. This repository supports GitPod (which is integrated into GitLab). This gives
   you a temporary, on-demand development environment with all your dependencies
   installed, for quick development on any computer. If you add this repository
   as a GitPod project, your environment will be pre-built for you for instant
   startup.

#. **(Not implemented yet)** *ARTIQ experiments are importable with
   absolute paths. Our ARTIQ fork includes an early merge of
   https://github.com/m-labs/artiq/pull/1805, enabling import of
   “repository” folder in this repository,
   e.g. ``from repository.mot import Load2DMot``. This makes your code
   more explicit and allows IDEs to provide code suggestions
   automatically.*

Initial setup
=============

To run this environment, you need a working Nix installation in a
Linux environment. Ideally, that means you're running Linux. If that's not
possible, you can run Nix in a WSL installation (e.g. Ubuntu) on Windows. For
the latter setup, you'll need to also have an ``artiq_ctlmgr`` running in
Windows which handles local devices. Details t.b.d., but see `the PyAION
documentation <https://aion-physics.gitlab.io/code/artiq/pyaion/>`__ for
more.

#. Install Nix (probably in single user mode).

#. Enable Nix flakes: paste "experimental-features = nix-command flakes" into
   `~/.config/nix/nix.conf`.

#. *(optional but recommended)* Install and configure cachix to benefit from
   pre-built binaries. Run `nix profile install nixpkgs#cachix` then `cachix use
   aion-physics`.

#. Done! Your environment is now totally defined by the flake: move on to
   :ref:`Launching ARTIQ`, or run `nix develop -c artiq_master --version` to
   test your installation.

Launching ARTIQ
===============

To run ARTIQ in the recommended "repository" mode, just run `nix run
.#run_artiq` in this repository. You'll need to launch a dashboard separately:
if you also want a dashboard, add `--gui` to the command.

To see the launch options, run `nix run .#run_artiq -- --help`

To debug in ARTIQ's file mode, use `nix run .#run_artiq -- --dev`.

To launch a shell in which all the ARTIQ dependencies are available, use `nix develop`.

Dependencies
============

Adding dependencies
-------------------

To add python dependencies to your ARTIQ environment, alter the list in
`requirements.in`. This automatically results in pinned package version in nix.
Once you've done this, run `nix run .#update_requirements` to automatically
regenerate the `requirements.txt` file, keeping it in sync with the pinned nix
packages.

Updating dependencies
---------------------

To update all packages to the latest version, use `nix flake update`. This will
remake your `flake.lock` file: once you've committed this file, future launches
will use the new package versions instead.

To update just the PyPI python dependencies, use `nix flake lock --update-input pypi-deps-db`.

To update just our internal packages, use:

`nix flake lock --update-input pyaion`

or

`nix flake lock --update-input icl_aion`

or

`nix flake lock --update-input artiq`

for those respective packages.

Documentation
=============

Documentation is generated from the files in the `docs` folder as well as the
docstring in your python code. The generator is Sphinx: see https://sphinx-doc.org for
details on the syntax.

This will be automatically compiled to a website on Gitlab Pages for each commit
to `master`, as well as compiled into a pdf (downloadable from the pipeline).

To preview documentation locally, run `nix run .#docs` to launch a webserver at http://127.0.0.1:8000.
