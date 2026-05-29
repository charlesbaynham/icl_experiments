from artiq.experiment import EnvExperiment
from artiq.experiment import TInt64
from artiq.experiment import TList
from artiq.language import kernel
from numpy import int64

from repository.lib.utils import FastIntChecksum


class KernelChecksumExperiment(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.checksummer = FastIntChecksum(self, 7)
        self.values = [int64(1), int64(2), int64(3), int64(4)]

    @kernel
    def run(self):
        self.do_checksum(self.values)

    @kernel
    def do_checksum(self, values: TList(TInt64)) -> TInt64:  # type: ignore[misc, valid-type]
        return self.checksummer.checksum(values)


def test_fast_int_checksum_compiles(build_and_run_experiment):
    build_and_run_experiment(KernelChecksumExperiment)


def test_fast_int_checksum_python_side(experiment_factory):
    exp = experiment_factory(KernelChecksumExperiment)
    exp.build()
    assert exp.checksummer.checksum([1, 2, 3, 4]) == 17
    assert exp.checksummer.checksum([1, 2, 3, 4]) != exp.checksummer.checksum(
        [1, 2, 3, 5]
    )
    assert exp.checksummer.checksum([1, 2, 3, 4]) != exp.checksummer.checksum([1, 2, 3])
