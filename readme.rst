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

Other features
==============

This repository is set up with features to help you maintain a healthy codebase
with a minimum of effort. The following features exist, and were set up
automatically by `pypackage template
<https://gitlab.com/aion-physics/code/pypackage-template>`_ (using this template
to set up later packages, e.g. for specific device drivers, will ensure
compatibility between all AION code, as well as encouraging some python best
practices).

This is an opinionated template - feel free to remove / change any of these
features as you prefer!

Version control
---------------

* **Your package will use git for version control**
  You probably already agree that this is a good idea if you're reading this message.


Virtual environment
-------------------

* **A Nix devShell is defined for you**
  This is a much stronger form of dependency management than pip environments, which you should prefer over virtual environments if possible. To launch a shell with your defined packages in scope, use `nix develop`. To add packages to your environment, edit `requirements.txt` and restart the shell.

* **This repository supports Nix + direnv**
  To automatically activate the Nix devShell when entering this directory, use direnv. See
  the `Nix documentation <https://nixos.wiki/wiki/Flakes#Direnv_integration>`_ for more information.

README
------

* **README should use reStructuredText format**
  This is the format used by most Python tools, is expected by
  `setuptools <https://setuptools.readthedocs.io>`_, and can be used by
  `Sphinx <http://sphinx-doc.org/>`_.

* **As few README files as possible**
  Additional README files (AUTHORS, CHANGELOG, etc) should be left to the user to create when necessary.

LICENSE
-------

* **No license**
  This template is aimed at projects which remain internal. If you later publish this code publicly, you should make sure to choose a license so others can use it legally.

`setup.py`
----------

* **Use setuptools**
  It's the standard packaging library for Python.
  `distribute` has merged back into `setuptools`, and `distutils` is less
  capable.
* **setup.py should not import anything from the package**
  When installing from source, the user may not have the packages dependencies installed, and importing the package is likely to raise an `ImportError`.
* **Dependencies are specified in `requirements.in`**
  This file specifies loose dependencies which are imported by `setup.py` when
  your package is installed. `requirements.in` should contain dependencies which
  are essential for your package to function. Note
  that you should prefer Nix-based environment management via `nix develop`, but
  setuptools-based installation is supported for e.g. Windows systems.

* **Dependencies are frozen by Nix** While `requirements.in` contains the list
  of dependencies for your project, this file should aim to be as
  nonrestrictive as possible in terms of the versions of the packages it
  requires. However, for reproducibility, it's useful to "freeze" the versions of
  packages used once you've got a project working so that you can always revisit
  a "known good" version. This template uses `nix flake` s for this purpose.
  These are also the versions used for CI testing. To update this list, just add
  a requirement to the `.in` file: it'll be resolved
  deterministically against the PyPI packages available when this repository was
  initiated. To include packages newer than this, run `nix flake update` to
  fetch the newest list, and commit the changes this makes to `flake.lock`.

Documentation
-------------

* **Use `sphinx <https://www.sphinx-doc.org/en/master/>`_**
  Sphinx is a powerful documentation tool which can produce documentation in
  many formats from the same input files. It can even be configured to parse
  your project's code and extract documentation from specially formatted
  comments, allowing you to keep the documentation right next to the code and
  reducing the risk of them becoming out-of-sync.
* **Use GitLab pages**
  Gitlab Pages lets you host a static html website associated with your project.
  This template will build your Sphinx documentation and host it at that
  location. By default, the Gitlab Page associated with your project has the
  same visibility as the project itself. The documentation will only be updated
  when you push to the master branch or tag a commit.
* **Compile to pdf**
  Sometime it's useful to have a pdf document with all the documentation for a
  project in it. The CI system will also compile your sphinx documentation to
  latex, and then compile that to pdf. The pdf will be available for download as
  an "artifact" for every commit.
* **Use `nix run .#docs` for testing**
  It's useful to quickly compile the documentation locally when you're writing
  it. To do this, run `nix run .#docs`.

Testing
-------

* **Uses** `pytest <https://docs.pytest.org>`_ **as the default test runner**
  This can be changed easily, though pytest is a easier, more powerful test
  library and runner than the standard library's unittest. Tests will be run
  automatically in Gitlab CI.
* **Define testing dependencies and `requirements.in`**
* **Use** `coverage <https://coverage.readthedocs.io/>`_ **for test coverage calculation**
  Receive a report of how much coverage your tests have in your codebase when
  you run them. This will be detected by Gitlab and shown alongside your commit.
* **Only run slow tests on the master branch or manually**
  Some unit tests are really slow: you don't want to run these for every single
  commit. You can mark your tests as slow using the decorator
  `@pytest.mark.slow`. These will only be run for:

  * Commits with a tag
  * When the user manually clicks the run button on the CI page
  * When a CI run is scheduled to be run repeatedly

* **`tests` directory should not be a package**
  The `tests` directory should not be a Python package unless you want to define
  some fixtures. But the best practices are to use `PyTest fixtures
  <https://docs.pytest.org/en/latest/fixture.html>`_ which provide a better
  solution. Therefore, the `tests` directory has no `__init__.py` file.

Linting
-------

* **Use** `black <https://black.readthedocs.io/en/stable/?badge=stable>`_ **for code styling**
  Code style is important: it makes it much easier for others to read your code.
  It's also boring and repetitive. `black` is a very opinionated code styler
  which makes all the decisions regarding code style, allowing you to focus on
  what you're actually writing. It will be run by the CI as a check stage.
* **Use** `pre-commit <https://pre-commit.com/>`_ **for automated styling** To
  prevent you from having to manually style your code, use `pre-commit` to
  configure your system to automatically run `black` every time you commit. To
  use it, run `pre-commit install`. This will also run automatically in the CI.
