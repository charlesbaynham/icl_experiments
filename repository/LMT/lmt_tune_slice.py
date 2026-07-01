from artiq.language import EnvExperiment


class NarrowDownAfterSlice(EnvExperiment):
    """
    Narrow down after slice

    Designed for tuning the SUServo offset to select v=0 atoms
    """

    def build(self):
        pass

    def run(self):
        raise NotImplementedError("Stub")
