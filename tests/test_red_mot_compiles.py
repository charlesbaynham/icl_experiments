import pytest


@pytest.mark.xfail(
    reason="Cameras are not mocked and will fail when tested not on the local network"
)
def test_red_mot(fragment_factory):
    from repository.measure_red_mot import MeasureBBRedMOTFrag

    def precompile(self):
        precompiled_setup = self.core.precompile(self.device_setup)
        precompiled_run = self.core.precompile(self.run_once)
        precompiled_cleanup = self.core.precompile(self.device_cleanup)

        print("Experiment was precompiled:")
        print(precompiled_setup)
        print(precompiled_run)
        print(precompiled_cleanup)

    setattr(MeasureBBRedMOTFrag, "precompile", precompile)

    exp = fragment_factory(MeasureBBRedMOTFrag)

    exp.host_setup()

    exp.precompile()
