"""
ICL_AION Readme
===============

**Provides a package of drivers for ARTIQ at ICL.**

*Charles Baynham 2022*

See `the documentation for PyAION
<https://aion-physics.gitlab.io/code/ARTIQ/pyaion/package-structure.html>`_ to
understand where this package fits in the overall AION structure.

This repository is:

#. **A Nix flake** - this means you can specify it as a dependency in other flakes, most
   importantly the ARTIQ experiment repositories that define experimental
   environments.

#. **A python package**  - this means that, when installed, this package is accessible from the
   python environment by using `import icl_aion`.

Purpose
=======

The purpose of this package is to contain system-specific code that isn't useful
to share in PyAION, but which must be in a package present at launch of
`artiq_master` instead of in an Experiment Repository which is loaded at launch
of each Experiment. If you can put code elsewhere, you should - the use of this
repository should be minimized to where necessary. Examples of such occasions include:

#. Defining the device_db for an institute (including peripheral devices and aliases)

#. Launching custom drivers which are not interesting enough / developed enough
   to deserve their own separate repositories.

#. Custom applets for plotting / UI in `artiq_dashboard`


Using this package with ARTIQ
-----------------------------

Your Experiment Repository is already set up to require this package, so this
package is already available to code stored there through the magic of Nix.
Launch an ARTIQ instance using the scripts in your Experiment Repository and
this package will be available to import.

Making updates
--------------

Nix flakes specify a specific version of every dependency which is stored in the
`flake.lock` file. This makes every experiment completely reproducible since its
entire environment is stored in the git history. It also means that if you make
changes to this repository, you need to a) push them back to gitlab and b) run
`nix flake update` in your Experiment Repository before they are available (then
restart ARTIQ).

Developing quickly
------------------

The process above will become tedious quickly if you're developing code in this
repository that you want to test live. There's no way around the requirement to
restart ARTIQ, but you can temporarily override Nix to use a local copy instead
of the gitlab one to avoid having to commit and push each time. To do this,
append `--override-flake icl_aion /path/to/local/version` to your nix develop
call you use to start ARTIQ - see the docs for your Experiment Repository for
more info.

Features
========

This repository is set up with features to help you maintain a healthy codebase
with a minimum of effort. The following features exist, and were set up
automatically by `pypackage template
<https://gitlab.com/aion-physics/code/pypackage-template>`_ (using this template
to set up later packages, e.g. for specific device drivers, will ensure
compatibility between all AION code, as well as encouraging some python best
practices).

Version control
---------------

* **Your package will use git for version control**
  You probably already agree that this is a good idea if you're reading this message.

* **Semantic package versioning is hard coded** The package version is defined
  by the `VERSION.json` file in the root of this project. The versioning system
  will also extract details from git to mark your packages with a hash of their
  most recent commit, and will be baked into any tarballs you create (e.g. for
  uploading to a PyPI registry). When updating the version, follow `semantic
  versioning guidelines <https://semver.org/>`_.

* **This package is installable as a Nix Flake**
  Nix is a functional package manager capable of building completely reproducible environments
  using packages and code in any programming language. The "nixpkgs" repository is both the largest
  and the most regularly updated software registry in the world. In short, Nix is very powerful and
  lets you build reproducible apps with fully explicit dependencies. This package is a Flake, which makes
  it independent of a centrally managed registry (or "channel"), and allows you full control over which
  updates are applied to your package's dependencies and when.

Virtual environment
-------------------

* **A `venv` will be created for you**
  Virtual environments are always a good idea with python. As part of the setup, this tool will create a virtual environment under `venv`, activate it and install the new package into it. If you prefer other environment managers (e.g. `conda`) then just delete or ignore the `venv` directory.

* **A Nix devShell is defined for you**
  This is a much stronger form of dependency management, which you should prefer over virtual environments if possible. To launch a shell with your defined packages in scope, use `nix develop`. To add packages to your environment, edit `requirements.txt` and restart the shell.

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
* **Dependencies are specified in `requirements.in` and `requirementsDev.in`**
  These files specify loose dependencies which are imported by `setup.py` when
  your package is installed. `requirements.in` should contain dependencies which
  are essential for your package to function and will be installed when your
  package is installed with `pip install --editable .`. `requirementsDev.in`
  should contain packages which are needed for developing your package (e.g.
  `pytest`) and can be installed by typing `pip install --editable .[dev]`. Note
  that you should prefer Nix-based environment management via `nix develop`, but
  setuptools-based installation is supported for e.g. Windows systems.

* **Dependencies are frozen by Nix** While `requirements.in` and
  `requirementsDev.in` contain the list of dependencies for your project, these
  files should aim to be as nonrestrictive as possible in terms of the versions
  of the packages they require. However, for reproducibility, it's useful to
  "freeze" the versions of packages used once you've got a project working so
  that you can always revisit a "known good" version. This template uses
  `nix flake` s for this purpose. These are also the versions used for CI testing. To
  update this list, just add a requirement to either of the `.in` files: it'll
  be resolved deterministically against the PyPI packages available when this
  repository was initiated. To include packages newer than this, run `nix flake
  update` to fetch the newest list, and commit the changes this makes to
  `flake.lock`.

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
* **Define testing dependencies in `requirementsDev.in` and `requirements.in`**
  Avoid duplicating dependency definitions, and use `requirementsDev.in` as the
  list of dependencies required for testing, but not for running your package.
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
* **Use** `pre-commit <https://pre-commit.com/>`_ **for automated styling**
  To prevent you from having to manually style your code, use `pre-commit` to
  configure your system to automatically run `black` every time you commit. This
  is not installed automatically since I don't want to alter your python
  environment without permission. To use it, run `pip install pre-commit &&
  pre-commit install`. This will also run automatically in the CI.

Authors
=======

`icl_aion` was written by `Charles Baynham <c.baynham@imperial.ac.uk>`_.

The `pypackage template <https://gitlab.com/aion-physics/code/pypackage-template>`_ from which this package was generated was written by Charles Baynham and inspired by `cookiecutter-pypackage-minimal <https://github.com/kragniz/cookiecutter-pypackage-minimal>`_

"""

__author__ = "Charles Baynham <c.baynham@imperial.ac.uk>"
__all__ = []
