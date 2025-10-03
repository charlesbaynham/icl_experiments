from artiq.experiment import EnvExperiment

from repository.lib.devices.clock_glitch_filter import ClockGlitchFilter


class TestClockGlitchFilterDeviceExp(EnvExperiment):

    def build(self):
        self.setattr_device("clock_glitch_filter")
        self.clock_glitch_filter: ClockGlitchFilter

    def run(self):
        print(self.clock_glitch_filter)
        print(self.clock_glitch_filter.get_identity())
