import numpy as np
from artiq.experiment import HasEnvironment
from artiq.experiment import TInt64
from artiq.experiment import TList
from artiq.language import portable
from numpy import int64


class SimpleRandom(HasEnvironment):
    """
    A simple, kernel-compatible random number generator for
    pseudo-random numbers in the range 0 to 1

    Adapted from chatgpt

    Example usage::

        from artiq.experiment import *

        class DoRandomThing(EnvExperiment):
            def build(self):
                seed = 12345  # Any integer seed
                self.rng = SimpleRandom(self, seed)

            @kernel
            def run(self):
                for _ in range(5):
                    print(self.rng.next())
    """

    def build(self, seed):
        # Constants for the Linear Congruential Generator (LCG)
        self.a = int64(1664525)  # Multiplier
        self.c = int64(1013904223)  # Increment
        self.m = int64(2) ** 32  # Modulus (2^32 for 32-bit)
        self.state = int64(seed)  # Initial state (seed)

        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("a")
        self.kernel_invariants.add("c")
        self.kernel_invariants.add("m")

    @portable(flags={"fast-math"})
    def next(self) -> float:
        # Linear Congruential Generator formula
        self.state = (self.a * self.state + self.c) % self.m
        return float(self.state) / float(self.m)  # Return a float in the range [0, 1)


class GaussianRandom(HasEnvironment):
    """
    A Gaussian random noise generator
    """

    def build(self, seed):
        self.rng = SimpleRandom(self, seed)

    @portable(flags={"fast-math"})
    def next(self) -> float:
        # Box-Muller transform
        u1 = self.rng.next()
        u2 = self.rng.next()
        z0 = (-2 * np.log(u1)) ** 0.5 * np.cos(2 * np.pi * u2)
        return z0


class FastIntChecksum:
    """
    A minimal rolling checksum for integer lists.

    This is intentionally just a 64-bit wrapping sum. It is not designed to be
    collision-resistant; it is designed to be cheap to compile and fast to run
    in ARTIQ kernels.
    """

    def __init__(self, seed: int = 0):
        self.initial = int64(seed)
        self.mask = int64(-1)

        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("initial")
        self.kernel_invariants.add("mask")

    @portable
    def checksum(self, values: TList(TInt64)) -> TInt64:  # type: ignore[misc, valid-type]
        checksum = self.initial

        for value in values:
            checksum = (checksum + value) & self.mask

        return checksum
