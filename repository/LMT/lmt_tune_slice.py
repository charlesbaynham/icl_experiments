from artiq.language import EnvExperiment


class _Stub(EnvExperiment):
    def build(self):
        pass

    def run(self):
        raise NotImplementedError("Stub")


class NarrowDownAfterSlice(_Stub):
    """
    Narrow down after slice

    Designed for tuning the SUServo offset to select v=0 atoms
    """


class NarrowUpAfterSlice(_Stub):
    """
    Narrow up after slice

    Designed for tuning the alpha Stark coefficient
    """
