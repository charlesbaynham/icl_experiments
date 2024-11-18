import numpy as np
from artiq.experiment import HasEnvironment
from artiq.experiment import portable
from numpy import int64


class SimpleRandom(HasEnvironment):
    """
    A simple, kernel-compatible random number generator for
    pseudo-random numbers in the range 0 to 1

    Adapted from chatgpt

    Example usage::

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
        self.m = int64(2) ** 64  # Modulus (2^64 for 64-bit)
        self.state = seed  # Initial state (seed)

        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("a")
        self.kernel_invariants.add("c")
        self.kernel_invariants.add("m")

    @portable(flags={"fast-math"})
    def next(self):
        # Linear Congruential Generator formula
        self.state = (self.a * self.state + self.c) % self.m
        return self.state / self.m  # Return a float in the range [0, 1)


class GaussianRandom(HasEnvironment):
    """
    A Gaussian random noise generator
    """

    def build(self, seed):
        self.rng = SimpleRandom(self, seed)

    @portable(flags={"fast-math"})
    def next(self):
        # Box-Muller transform
        u1 = self.rng.next()
        u2 = self.rng.next()
        z0 = (-2 * np.log(u1)) ** 0.5 * np.cos(2 * np.pi * u2)
        return z0
