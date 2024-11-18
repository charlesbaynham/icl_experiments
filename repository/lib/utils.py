from artiq.experiment import HasEnvironment
from artiq.experiment import portable


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
        self.a = 1664525  # Multiplier
        self.c = 1013904223  # Increment
        self.m = 2**32  # Modulus (2^32 for 32-bit)
        self.state = seed  # Initial state (seed)

    @portable(flags={"fast-math"})
    def next(self):
        # Linear Congruential Generator formula
        self.state = (self.a * self.state + self.c) % self.m
        return self.state / self.m  # Return a float in the range [0, 1)
