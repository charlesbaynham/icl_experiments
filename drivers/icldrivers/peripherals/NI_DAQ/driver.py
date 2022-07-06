import nidaqmx


class NIDAQDigitalOut:
    """
    Driver for an NI DAQ digital output
    """

    def __init__(self, *args, physical_channel=None, simulation=False):
        if simulation:
            raise NotImplementedError
        self.physical_channel = physical_channel

    def ping(self):
        """
        The all-important ping function, without which ARTIQ will brutally kill our controller.
        """
        return True

    def write(self, val):
        with nidaqmx.Task() as task:
            task.do_channels.add_do_chan(self.physical_channel)
            task.write(val, auto_start=True)


class NIDAQAnalogIn:
    """
    Driver for an NI DAQ analog input
    """

    def __init__(self, *args, physical_channel=None, simulation=False):
        if simulation:
            raise NotImplementedError
        self.physical_channel = physical_channel

    def ping(self):
        """
        The all-important ping function, without which ARTIQ will brutally kill our controller.
        """
        return True

    def read(self):
        with nidaqmx.Task() as task:
            task.ai_channels.add_ai_voltage_chan(self.physical_channel)
            task.timing.samp_clk_rate = 1000  # arbitarily set 1kHz as the sample rate

            return task.read()

    def readN(self, N, rate=1000):
        """Read N readings"""
        with nidaqmx.Task() as task:
            task.ai_channels.add_ai_voltage_chan(self.physical_channel)
            task.timing.samp_clk_rate = rate

            return task.read(N)
