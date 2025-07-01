from pathlib import Path
from typing import Callable

import matplotlib
from artiq.experiment import *

from repository.lib.utils import GaussianRandom
from repository.lib.utils import SimpleRandom

matplotlib.use("Agg")  # Use a non-interactive backend for matplotlib
import matplotlib.pyplot as plt


class RandomNumbersUniform(EnvExperiment):
    def build(self):
        seed = 12345  # Any integer seed
        self.rng = SimpleRandom(self, seed)

    @portable
    def run(self):
        nums = []
        for _ in range(10000):
            x = self.rng.next()
            nums.append(x)
            print(x)

        plt.hist(nums, bins=20)
        plt.savefig(Path(__file__, "..", "random_numbers_uniform.png").resolve())


class RandomNumbersGaussian(EnvExperiment):
    def build(self):
        seed = 12345  # Any integer seed
        self.rng = GaussianRandom(self, seed)

    @portable
    def run(self):
        nums = []
        for _ in range(10000):
            x = self.rng.next()
            nums.append(x)
            print(x)

        plt.hist(nums, bins=20)
        plt.savefig(Path(__file__, "..", "random_numbers_gaussian.png").resolve())


def test_random_numbers_uniform(build_and_run_experiment: Callable[..., None]):
    build_and_run_experiment(RandomNumbersUniform)


def test_random_numbers_gaussian(build_and_run_experiment: Callable[..., None]):
    build_and_run_experiment(RandomNumbersGaussian)
