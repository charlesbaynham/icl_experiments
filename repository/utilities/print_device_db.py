from pprint import pprint

from artiq.experiment import EnvExperiment


class PrintDeviceDB(EnvExperiment):
    """Print the device database."""

    def build(self):
        pass

    def run(self):
        device_db = self.get_device_db()

        print("*" * 20)
        print("Device database:")
        print("*" * 20)
        pprint(device_db)
