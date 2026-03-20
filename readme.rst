Readme
######

**The Imperial ARTIQ experiments repository.**

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

#. This repository uses poetry2nix to handle python dependencies. Compared to
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

#. ARTIQ experiments are importable with
   absolute paths. Our ARTIQ fork includes an early merge of
   https://github.com/m-labs/artiq/pull/1805, enabling import of
   “repository” folder in this repository,
   e.g. ``from repository.mot import Load2DMot``. This makes your code
   more explicit and allows IDEs to provide code suggestions
   automatically.

Updates
=======

To update to the latest version of pyaion / artiq, use::

   nix run .#update

This will update both nix and poetry inputs, keeping them in sync.

If you just want to your python packages, run::

   poetry update

or e.g. to update just one::

   poetry update numpy


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


Testing
=======

Unit tests are enabled and highly recommended. While testing code that
interacts with the ARTIQ kernel is difficult, testing utility functions is done
via pytest. To run tests locally::

   nix run .#pytest

To run a specific test or test file, pass arguments::

   nix run .#pytest -- -k test_name

Updating test durations
-----------------------

The CI uses pytest-split to distribute tests across parallel runners based on
their duration. The test duration data is stored in `.test_durations` and should
be updated periodically to ensure optimal test distribution. To update it, run::

   nix run .#pytest -- --store-durations

Then commit the updated `.test_durations` file.



Dependencies
============

Adding dependencies
-------------------

To add python dependencies to your ARTIQ environment, run e.g.::
   poetry add my-package

to alter the spec in `pyproject.toml`.
This automatically results in pinned package versions in nix.


Documentation
=============

Documentation is generated from the files in the `docs` folder as well as the
docstring in your python code. The generator is Sphinx: see https://sphinx-doc.org for
details on the syntax.

This will be automatically compiled to a website on Gitlab Pages for each commit
to `master`, as well as compiled into a pdf (downloadable from the pipeline).

To preview documentation locally, run `nix run .#docs` to launch a webserver at
http://127.0.0.1:8000.

To-do list
==========

This repository uses the convention that to-do items are marked with the string
"TO<removeme>DO". Temporary bodges which should be not be left in the code for
longer than a few hours are marked with "FIX<removeme>ME". These will cause the
Gitlab pipeline to fail, to remind you to remove them. Get rid of the
"<removeme>" bit! We need that here otherwise the pipeline would fail.

You can use e.g. the "TodoTree" extension to extract a list of these.

Here are some which don't fit into obvious locations in the code:

TODO: Merge camera imaging so that only one applet is created per camera
TODO: Figure out how to not broadcast massive ndscan datasets to every client
TODO: Blow away atoms in spectroscopy sequence, and reimage the remaining ones
TODO: The ARTIQ release notes claim "Support for WRPLL low-noise clock recovery" - use it!

TODO: SED upgrade exploration:

   The SED update in ARTIQ-8 broke our sequences by introducing event spreading
   for DRTIO crates. We can recover past behavior by disabling this, but better
   would be a SED upgrade. Can't we ship events to the lane with the highest
   negative delta? That seems like it would work.

   The algorithm would be:
   * Keep track of the highest timestamps in all the lanes (this happens already)
   * Subtract our current event's timestamp to calculate the slack
   * Set all events with timestamps < 0 to infinity (underflow here if all are < 0)
   * Perform a combinatorial sort using a BitonicSort from migen
   * Choose the first item, i.e. the lane with the smallest amount of positive slack

   Have I missed a problem with this? Potential problems:

   * All these steps can be done combinatorially, but they might still be too
     gate-heavy to work. Maybe vivado will throw a wobbly.

   * I don't know much about the SED code and I don't understand why it
     currently uses 4 syncronous cycles - I'd have thought you could do it with
     fewer. My ignorance might be limiting my ability to foresee problems...


Authors
=======

`ICL_experiments` was written by `Charles Baynham
<c.baynham@imperial.ac.uk>`_.

The `template
<https://gitlab.com/aion-physics/code/artiq/pyaion>`_
from which this package was generated was written by Charles Baynham.
