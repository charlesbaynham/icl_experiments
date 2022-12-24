"""
Non-core devices
================

This module is used to list all the peripheral devices that the ARTIQ system
needs to interact with, i.e. anything that's not part of the Sinara crate.

These have two types:

1. Local devices - these represent python objects which will be initiated at the
   start of each Experiment and passed to your code.

2. Controllers - these are NDSP controllers which are created when ARTIQ is
   launched. Interfaces to these are passed to your experiment and communication
   happens over the network. These can therefore run on computers other than the
   main `artiq_master` host, and even on different operating systems.
"""
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def get_non_core_devices(simulation_mode=False):

    if simulation_mode:
        logger.warning("Initiating devices in simulation mode")

    _non_core = {
        # InfluxDB loggers - you should probably keep these. They are commented
        # out though because they'll throw error messages unless you have an
        # influx DB server running on this server. If you do, it should probably
        # also be managed by Nix - speak to Charles and tell him what you did so
        # we can compare notes!
        "influx_logger": {
            "type": "controller",
            "host": "::1",
            "port": "3276",
            "target": "influx_logger",
            "command": "artiq_influx_generic --port {port} --bind {bind}",
        },
        "influx_scheduler_logger": {
            "type": "controller",
            "host": "::1",
            "port": "3275",
            "command": "artiq_influxdb_schedule --port-control {port} --bind {bind}",
        },
        "artiq_http": {
            "type": "controller",
            "host": "::1",
            "port": "8000",
            "command": "aqctl_artiq_http",
        },
        # Example devices: edit to suit your lab
        # An example of a local device:
        # "SomeCurrentDriver": {
        #     "type": "local",
        #     "module": "icldrivers.peripherals.TTI_QL335TP",
        #     "class": "TTI_QL335TP",
        #     "arguments": {
        #         "id": "USB VID:PID=103E:03E8 SER=TT29WXY4A",
        #         "simulation": simulation_mode,
        #     },
        # },
        # An example of a controller device:
        # This is commented out since otherwise you'll get error messages
        # because you don't have this device in your lab.
        # "AnotherCurrentDriver": {
        #     "type": "controller",
        #     "host": "::1",
        #     "port": "3303",
        #     "target": "TTIPowerSupply",
        #     "command": 'aqctl_TTIPowerSupply --port {port} --bind {bind} --id "USB VID:PID=103E:03E8 SER=TTTEO7KJA"',
        # },
        # An example of connecting to a Toptica DLC Pro
        # "ATopticaDLCPro": {
        #     "type": "local",
        #     "module": "icldrivers.peripherals.TopticaDLCPro",
        #     "class": "TopticaDLCPro",
        #     "arguments": {
        #         "ip": "1.2.3.4",
        #         "laser": "laser1",
        #         "simulation": simulation_mode,
        #     },
        # },
    }

    return _non_core


if __name__ == "__main__":
    import pprint

    pprint.pprint(get_non_core_devices())
