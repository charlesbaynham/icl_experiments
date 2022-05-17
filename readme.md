ICL Experiments
===============

__The Imperial ARTIQ experiments repository.__

This repository contains the Imperial ARTIQ experiments, and also defines the software environment in which the Imperial ARTIQ system runs. It is a nix flake: to launch ARTIQ, run the script ./run_artiq.sh. This repository has an opinionated structure and provides the following features, in approximately descending order of importance:

1. This is one of several repositories that make up the complete Imperial ARTIQ installation. For the complete structure, see [the PyAION documentation](https://aion-physics.gitlab.io/code/artiq/pyaion/). 

2. This is a nix flake. That means that the build environment is fully defined, including versions of both python and system packages. Updates / additions are explicit and are recorded in the git history, a hash of which in included in the metadata of every dataset taken. For more information on how to add / update packages in your installation, see the Managing packages section below. 

3. Definition of the ARTIQ + peripherals hardware happens elsewhere, in the institute-specific python packages. See [the PyAION documentation](https://aion-physics.gitlab.io/code/artiq/pyaion/) for details. 

4. Code in this repository can be automatically styled using pre-commit by running `pre-commit run --all`. Alternatively, use `pre-commit install` to enable automatic formatting on every commit. 

5. Documentation for this repository is build using Sphinx. It is also auto-generated from Experiment files, so write your docstrings in the Google format. 

6. Unit tests are enabled and highly recommended. Testing code that interacts with the ARTIQ kernel is still nigh-on impossible (though speak to Riverlane if you're interested in their early-access realtime simulator), but testing other utility functions is done via `pytest`. 

7. Linting checks, documentation building and unit tests will be run automatically using Gitlab CI. 

8. __(Not implemented yet)__ _ARTIQ experiments are importable with absolute paths. Our ARTIQ fork includes an early merge of https://github.com/m-labs/artiq/pull/1805, enabling import of "experiments" folder in this repository, e.g. `from experiments.mot import Load2DMot`. This makes your code more explicit and allows IDEs to provide code suggestions automatically. It has the unfortunate downside of making all experiments appear under an "experiments" top-level entry. If you agree with me that this is annoying, consider helping me argue the case in https://github.com/m-labs/artiq/issues/1543._
