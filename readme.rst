Readme
######

**The ICL ARTIQ experiments repository.**

This repository holds the ARTIQ experiments, imported by ARTIQ as an
"experiment repository" and whose hash is embedded into datasets. This
also includes a complete Nix definition of the working environment
required to run ARTIQ, thus pinning all dependencies as well.

Overview
========

This repository contains the ICL ARTIQ experiments, and also defines the
software environment in which the ICL ARTIQ system runs. It is a nix flake:
to launch ARTIQ, see the :ref:`Launching ARTIQ` section below. This repository has an
opinionated structure and provides the following features, in approximately
descending order of importance:

#. This is one of several repositories that make up the complete ICL ARTIQ
   installation. For the complete structure, see `the PyAION documentation
   <https://aion-physics.gitlab.io/code/artiq/pyaion/>`__.

#. This is a nix flake. That means that the build environment is fully
   defined, including versions of both python and system packages.
   Updates / additions are explicit and are recorded in the git history,
   a hash of which in included in the metadata of every dataset taken.
   For more information on how to add / update packages in your
   installation, see the Managing packages section below.

#. Definition of your ARTIQ + peripherals hardware happens in `device_db_config`.
   See `the PyAION documentation <https://aion-physics.gitlab.io/code/artiq/pyaion/>`__
   for details.

#. The ARTIQ stack uses
  `ndscan <https://github.com/OxfordIonTrapGroup/ndscan>`__. This allows us to handle
   complexity without giving up deep control of our experiments.

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

Updates
=======

To update to the latest version of PyAION, use `nix flake lock --update-input pyaion`.

Contributing
============

As much as possible, all common functionality is implemented in the PyAION
package instead of here. This means that improvements can be shared easily
across institutions, and also reduces our divergence.

When making changes / adding functionality, please consider whether you can make
them in PyAION instead of in your local package. If you do so, we'll all have a
common interface and will be able to benefit from the work of others.

We're yet to define the full layout of the control system (as of 2022-11-16) so
this repository currently contains very little of use. As the structure becomes
more defined it'll be coded in PyAION. To use that code, you'll need to add
snippets to this repository (like the one in `set_suservo_static.py`).

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

#. *(optional but strongly recommended)* Install and configure cachix to benefit
   from pre-built binaries. Run `nix profile install nixpkgs#cachix` then
   `cachix use aion-physics`. This allows your ARTIQ setup to pull pre-built
   environments from our GitLab CI pipelines, saving you ~2 hours for the first
   run after an update.

#. Done! Your environment is now totally defined by the flake: move on to
   :ref:`Launching ARTIQ`, or run `nix develop -c artiq_master --version` to
   test your installation.

Launching ARTIQ
===============

Basic usage
-----------

To enter an environent with ARTIQ available, use `nix develop`. This will give
you an environent with all the required packages installed for you to be able to
run commands like `artiq_master`. This is the starting point for all the
examples in the ARTIQ manual.

To run ARTIQ in the recommended "repository" mode, use::

  artiq_session -m=--git -m=--repository -m=. -m=--experiment-subdir -m=repository

Full stack usage
----------------

ARTIQ is at its best when supported by a stack of complimentary software. For
example, you might require an InfluxDB database and a Grafana interface to it.
Or, you might want to make regular backups to an onsite location (see the
icl_experiments repository for an example of this).

To support this behaviour reproducably, this repository contains a session
manager which will launch a pre-defined stack of software, currently consisting
of:

* ARTIQ (master and controller manager)
* NDScan janitor
* InfluxDB
* Grafana

To launch this stack, use `nix run .#full_stack` or run the script in this
repository called `run_artiq.sh`.

Development usage
-----------------

Nix environments are 100% reproducable which makes them excellent for performing
well-defined experiments. However, when debugging / developing, it's often
useful to run in a less strict environment where python packages can be quickly
installed / edited (e.g. using pip's `pip install --editable` option).

For this purpose, there is an alternative devShell available called "artiqDev" which can be entered via::

  nix develop .#artiqDev

__Do not use this for normal usage!__ Doing so will break the reproducibility
guarantees which Nix otherwise provides and will mean than changes you make to
your environment cannot be used by others. You have been warned...

Dependencies
============

Adding dependencies
-------------------

To add python dependencies to your ARTIQ environment, alter the list in
`requirements.in`. This automatically results in pinned package version in nix.
Once you've done this, run `nix run .#update_requirements` to automatically
regenerate the `requirements.txt` file, keeping it in sync with the pinned nix
packages.

If you forget to do this, the CI pipeline will remind you by having one of the
jobs fail.

Updating dependencies
---------------------

To update all packages to the latest version, use `nix flake update`. This will
remake your `flake.lock` file: once you've committed this file, future launches
will use the new package versions instead.

Note that since packages are pinned to a common version by PyAION, this will
just update you to the latest AION pin. If you need a specific package for some
reason, you should add it as a requirement bound in your requirements.in file. E.g.::

  some-unusual-package >= 3.1

Documentation
=============

Documentation is generated from the files in the `docs` folder as well as the
docstring in your python code. The generator is Sphinx: see https://sphinx-doc.org for
details on the syntax.

This will be automatically compiled to a website on Gitlab Pages for each commit
to `master`, as well as compiled into a pdf (downloadable from the pipeline).

To preview documentation locally, run `nix run .#docs` to launch a webserver at
http://127.0.0.1:8000.

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

See the documentation for `pypackage template
<https://gitlab.com/aion-physics/code/pypackage-template>`_ for details of
these.

Authors
=======

`icl_experiments` was written by `Charles Baynham
<c.baynham@imperial.ac.uk>`_.

The `template
<https://gitlab.com/aion-physics/code/artiq/device-packages/aion-experiments-template>`_
from which this package was generated was written by Charles Baynham and
inspired by `cookiecutter-pypackage-minimal
<https://github.com/kragniz/cookiecutter-pypackage-minimal>`_
