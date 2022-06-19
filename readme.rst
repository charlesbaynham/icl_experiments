Imperial ARTIQ Experiments
==========================

**The Imperial ARTIQ experiments repository.**

This repository holds the ARTIQ experiments, imported by ARTIQ as an
“experiment repository” and whose hash is embedded into datasets. This
also includes a complete Nix definition of the working environment
required to run ARTIQ, thus pinning all dependencies as well. The one
remaining item of information that's not recorded is the bitstream
version running on the Sinara core. It's t.b.d. how we manage this.
(TODO)

Overview
========

This repository contains the Imperial ARTIQ experiments, and also
defines the software environment in which the Imperial ARTIQ system
runs. It is a nix flake: to launch ARTIQ, run the script ./run_artiq.sh.
This repository has an opinionated structure and provides the following
features, in approximately descending order of importance:

0. To run this environment, you need a working Nix installation in a
   Linux environment. Ideally, that means you're running Linux. If
   that's not possible, you can run Nix in a WSL installation
   (e.g. Ubuntu) on Windows. For the latter setup, you'll need to also
   have an ``artiq_ctlmgr`` running in Windows which handles local
   devices. Details t.b.d., but see `the PyAION
   documentation <https://aion-physics.gitlab.io/code/artiq/pyaion/>`__
   for more.

1. This is one of several repositories that make up the complete
   Imperial ARTIQ installation. For the complete structure, see `the
   PyAION
   documentation <https://aion-physics.gitlab.io/code/artiq/pyaion/>`__.

2. This is a nix flake. That means that the build environment is fully
   defined, including versions of both python and system packages.
   Updates / additions are explicit and are recorded in the git history,
   a hash of which in included in the metadata of every dataset taken.
   For more information on how to add / update packages in your
   installation, see the Managing packages section below.

3. Definition of the ARTIQ + peripherals hardware happens elsewhere, in
   the institute-specific python packages. See `the PyAION
   documentation <https://aion-physics.gitlab.io/code/artiq/pyaion/>`__
   for details.

4. Code in this repository can be automatically styled using pre-commit
   by running ``pre-commit run --all``. Alternatively, use
   ``pre-commit install`` to enable automatic formatting on every
   commit.

5. This repository supports direnv, and uses its Nix / flake
   integration. This means that (if desired) you can automatically enter
   the ARTIQ environment every time you ``cd`` into this folder, or open
   Visual Studio Code in it (install the direnv extension). See
   https://direnv.net/ for details.

6. Documentation for this repository is build using Sphinx. It is also
   auto-generated from Experiment files, so write your docstrings in the
   Google format.

7. Unit tests are enabled and highly recommended. Testing code that
   interacts with the ARTIQ kernel is still nigh-on impossible (though
   speak to Riverlane if you're interested in their early-access
   realtime simulator), but testing other utility functions is done via
   ``pytest``.

8. Linting checks, documentation building and unit tests will be run
   automatically using Gitlab CI.

9. **(Not implemented yet)** *ARTIQ experiments are importable with
   absolute paths. Our ARTIQ fork includes an early merge of
   https://github.com/m-labs/artiq/pull/1805, enabling import of
   “repository” folder in this repository,
   e.g. ``from repository.mot import Load2DMot``. This makes your code
   more explicit and allows IDEs to provide code suggestions
   automatically.*

Launching ARTIQ
===============

To run ARTIQ in the recommended “repository” mode, just run
``./run_artiq.sh`` in this repository.

To debug in ARTIQ's file mode, use ``nix develop`` and then launch
``artiq_master`` as you prefer, or use ``nix develop -c artiq_master``.
