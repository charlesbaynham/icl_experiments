from artiq.experiment import *
from repository.lib.utils import SimpleRandom
import matplotlib.pyplot as plt
from pathlib import Path

OUTFILE = Path(__file__, "..", "random_numbers.png").resolve()


class RandomNumbers(EnvExperiment):
    def build(self):
        seed = 12345  # Any integer seed
        self.rng = SimpleRandom(self, seed)

    @portable
    def run(self):
        nums = []
        for _ in range(1000):
            x = self.rng.next()
            nums.append(x)
            print(x)

        plt.hist(nums, bins=20)
        plt.savefig(OUTFILE)


def test_random_numbers(build_and_run_experiment):
    build_and_run_experiment(RandomNumbers)
