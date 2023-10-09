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

port_iterator = iter(range(3278, 99999))
get_next_port = lambda: int(next(port_iterator))

PORT_WAND_CONTROL = 3276
PORT_WAND_NOTIFY = 3277


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
            "best_effort": True,
            "host": "::1",
            "port": get_next_port(),
            "target": "influx_logger",
            "command": "artiq_influx_generic --port {port} --bind {bind}",
        },
        "influx_scheduler_logger": {
            "type": "controller",
            "best_effort": True,
            "host": "::1",
            "port": get_next_port(),
            "command": "artiq_influxdb_schedule --port-control {port} --bind {bind}",
        },
        "wand_server": {
            "type": "controller",
            "best_effort": True,
            "host": "::1",
            "port": PORT_WAND_CONTROL,
            "command": (
                "bash -c '"
                "WLM_DATA_PATH=/etc/HighFinesse/libwlmData.so "
                "nix run .#wand_server -- -n icl_aion --bind \\* "
                f"--port-notify {PORT_WAND_NOTIFY} "
                f"--port-control {PORT_WAND_CONTROL}"
                "'"
            ),
        },
        # "artiq_http": {
        #     "type": "controller",
        #     "host": "::1",
        #     "port": "8000",
        #     "command": "aqctl_artiq_http",
        # },
        "blue_IJD1_controller": {
            "type": "controller",
            "best_effort": True,
            "host": "::1",
            "port": get_next_port(),
            "command": f"aqctl_koheron_ctl200_laser_driver {'--simulation-mode' if simulation_mode else ''} --port {{port}} --bind {{bind}} --id 'USB VID:PID=0403:6015 SER=DT0405C1'",
        },
        "blue_IJD2_controller": {
            "type": "controller",
            "best_effort": True,
            "host": "::1",
            "port": get_next_port(),
            "command": f"aqctl_koheron_ctl200_laser_driver {'--simulation-mode' if simulation_mode else ''} --port {{port}} --bind {{bind}} --id 'USB VID:PID=0403:6015 SER=DT04051V'",
        },
        "blue_IJD3_controller": {
            "type": "controller",
            "best_effort": True,
            "host": "::1",
            "port": get_next_port(),
            "command": f"aqctl_koheron_ctl200_laser_driver {'--simulation-mode' if simulation_mode else ''} --port {{port}} --bind {{bind}} --id 'USB VID:PID=0403:6015 SER=DT040D35'",
        },
        "red_IJD1_controller": {
            "type": "controller",
            "best_effort": True,
            "host": "::1",
            "port": get_next_port(),
            "command": f"aqctl_koheron_ctl200_laser_driver {'--simulation-mode' if simulation_mode else ''} --port {{port}} --bind {{bind}} --id 'USB VID:PID=0403:6015 SER=DT040081'",
        },
        "flir_camera_ch2_horizontal": {
            "type": "local",
            "module": "repository.lib.fragments.flir_camera_shim",
            "class": "Camera",
            "arguments": {
                "name": "FLIR-Blackfly S BFS-PGE-50S5M-22018873",
                "loglevel": logger.getEffectiveLevel(),
            },
        },
        "flir_camera_ch2_vertical": {
            "type": "local",
            "module": "repository.lib.fragments.flir_camera_shim",
            "class": "Camera",
            "arguments": {
                "name": "FLIR-Blackfly S BFS-PGE-50S5M-22018872",
                "loglevel": logger.getEffectiveLevel(),
            },
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
