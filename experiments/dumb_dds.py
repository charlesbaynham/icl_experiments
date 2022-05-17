# Copied from https://programtalk.com/vs2/?source=python/7771/artiq/artiq/examples/master/repository/utilities/dds_setter.py
# Modified by CFAB

import re
 
from artiq.experiment import EnvExperiment, NumberValue, kernel, delay, ms
 
 
class DDSSetter(EnvExperiment):
    """DDS Setter"""
    def build(self):
        self.setattr_device("core")
 
        self.dds = dict()
 
        device_db = self.get_device_db()

        for k, v in device_db.items():
            try:
                print(f"{k} - type = {v['type']}, module = {v['module']}, class = {v['class']}")
            except KeyError:
                print(f"Failed on {k}")

            if (isinstance(v, dict)
                    and v["type"] == "local"
                    and v["module"] == "artiq.coredevice.ad9910"
                    and v["class"] in ("AD9910",)
            ):
                self.dds[k] = {
                    "driver": self.get_device(k),
                    "frequency": self.get_argument(
                        "{}_frequency".format(k),
                        NumberValue(100e6, scale=1e6, unit="MHz", ndecimals=6))
                }
 
    @kernel
    def set_dds(self, dds, frequency):
        dds.set(frequency)
        delay(200*ms)
 
    def run(self):
        for k, v in self.dds.items():
            self.set_dds(v["driver"], v["frequency"])
