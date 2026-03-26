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
import os

# Get the IP address for connecting to the ARTIQ master from the environment
# variable ARTIQ_CONNECTION_IP.
ARTIQ_CONNECTION_IP = os.getenv("ARTIQ_CONNECTION_IP", "::1")


logger = logging.getLogger(__name__)


port_iterator = iter(range(3278, 99999))
get_next_port = lambda: int(next(port_iterator))

PORT_WAND_CONTROL = 3276
PORT_WAND_NOTIFY = 3277

# N.B. this needs to be in sync with the hard-coded value in
# `icl_aion_server_config.pyon`
PORT_GAIO_WAND_DRIVER = 4001


def get_non_core_devices(simulation_mode=False):
    if simulation_mode:
        logger.warning("Initiating devices in simulation mode")

    _non_core = {
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
            "command": (
                "artiq_influxdb_schedule "
                f"--server-master {ARTIQ_CONNECTION_IP} "
                "--port-control {port} "
                "--bind {bind}"
            ),
        },
        "wand_server": {
            "type": "controller",
            "best_effort": True,
            "host": ARTIQ_CONNECTION_IP,
            "port": PORT_WAND_CONTROL,
            "command": (
                "bash -c '"
                "WLM_DATA_PATH=/etc/HighFinesse/libwlmData.so "
                "nix run .#wand_server -- -n icl_aion --no-localhost-bind --bind {bind} "
                f"--port-notify {PORT_WAND_NOTIFY} "
                f"--port-control {PORT_WAND_CONTROL} "
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
        "blue_relocker": {
            "type": "controller",
            "best_effort": True,
            "host": "::1",
            "port": get_next_port(),
            "command": f"aqctl_relocker_driver --port {{port}} --bind {{bind}} --id 'USB VID:PID=0403:6001 SER=AQ01QRMM'",
        },
        "red_relocker": {
            "type": "controller",
            "best_effort": True,
            "host": "::1",
            "port": get_next_port(),
            "command": f"aqctl_relocker_driver --port {{port}} --bind {{bind}} --id 'USB VID:PID=0403:6001 SER=AQ01QR9I'",
        },
        "gaio_wand_driver_688": {
            "type": "controller",
            "best_effort": True,
            "host": "::1",
            "port": PORT_GAIO_WAND_DRIVER,
            "command": f"aqctl_gaio_laser_driver --port {{port}} --bind {{bind}} --id 'USB VID:PID=0403:6001 SER=AG0KOVMA'",
        },
        # Removed: this has changed its firmware and no longer need to be run in ARTIQ (I should put back control of it though)
        # "cavity_scanner": {
        #     "type": "controller",
        #     "best_effort": True,
        #     "host": "::1",
        #     "port": get_next_port(),
        #     "command": f"aqctl_relocker_driver --port {{port}} --bind {{bind}} --id 'USB VID:PID=0403:6001 SER=AQ01QRN0'",
        # },
        # "test_relocker": {
        #     "type": "controller",
        #     "best_effort": True,
        #     "host": "::1",
        #     "port": get_next_port(),
        #     "command": f"aqctl_relocker_driver {'--simulation-mode' if simulation_mode else ''} --port {{port}} --bind {{bind}} --id 'USB VID:PID=0403:6001 SER=AQ01QRN2'",
        # },
        "flir_camera_ch2_horizontal": {
            "type": "local",
            "module": "repository.lib.fragments.cameras.flir_camera_shim",
            "class": "Camera",
            "mockmodule": "repository.lib.fragments.cameras.flir_camera_shim",
            "mockclass": "MockCamera",
            "arguments": {
                "name": "FLIR-Blackfly S BFS-PGE-50S5M-23476914",
                "loglevel": logging.WARNING,
            },
        },
        "flir_camera_ch2_vertical": {
            "type": "local",
            "module": "repository.lib.fragments.cameras.flir_camera_shim",
            "class": "Camera",
            "mockmodule": "repository.lib.fragments.cameras.flir_camera_shim",
            "mockclass": "MockCamera",
            "arguments": {
                "name": "FLIR-Blackfly S BFS-PGE-50S5M-22018872",
                "loglevel": logging.WARNING,
            },
        },
        "rigol_counter": {
            "type": "local",
            "module": "repository.lib.fragments.rigol.rigol_device",
            "class": "RigolCounter",
            "arguments": {
                "rigol_ip": "rigol-dg4162-b.lan",
                "gate_time": "10 s",
            },
            "mockmodule": "repository.lib.fragments.rigol.rigol_device",
            "mockclass": "MockRigolCounter",
        },
        "clock_glitch_filter": {
            "type": "controller",
            "best_effort": True,
            "host": "::1",
            "port": get_next_port(),
            "command": (
                "python -m repository.lib.devices.aqctl_clock_glitch_filter"
                " --port {port}"
                " --bind {bind}"
                " --id 'USB VID:PID=0403:6001 SER=AG0KOVMB'"
            ),
        },
        "andor_camera": {
            "type": "controller",
            "host": "labpc1.lan",
            "port": 7777,
            "target": "AndorDriver",
            "mockmodule": "repository.lib.fragments.cameras.andor_mock",
            "mockclass": "MockAndorCamera",
            "command": 'aqctl_andor_cam --port {port} --bind {bind} --id "AndorCam" --temperature -60 --fan_mode "full"',
        },
        "chamber_1_axial_coil_driver": {
            "type": "local",
            "module": "tenma_power_supply",
            "class": "TENMAPowerSupply",
            "mockmodule": "unittest.mock",
            "mockclass": "MagicMock",
            "arguments": {
                "id": "tenma-powersupply-1.lan",
                "port": 18200,
                "simulation": simulation_mode,
            },
        },
        "chamber_1_radial1_coil_driver": {
            "type": "local",
            "module": "tenma_power_supply",
            "class": "TENMAPowerSupply",
            "mockmodule": "unittest.mock",
            "mockclass": "MagicMock",
            "arguments": {
                "id": "tenma-aion-ch1-1.lan",
                "port": 18202,
                "simulation": simulation_mode,
            },
        },
        "chamber_1_radial2_coil_driver": {
            "type": "local",
            "module": "tenma_power_supply",
            "class": "TENMAPowerSupply",
            "mockmodule": "unittest.mock",
            "mockclass": "MagicMock",
            "arguments": {
                "id": "tenma-aion-ch1-2.lan",
                "port": 18203,
                "simulation": simulation_mode,
            },
        },
        "chamber_1_radial_coil_driver": {
            "type": "local",
            "module": "tti_power_supply",
            "class": "TTIPowerSupplyTCP",
            "arguments": {
                "id": "10.137.1.28",
                "simulation": simulation_mode,
            },
        },
        "toptica_461": {
            "type": "local",
            "module": "toptica_wrapper.driver",
            "class": "TopticaDLCPro",
            "arguments": {
                "ip": "toptica-461-679",
                "laser": "laser1",
                "simulation": simulation_mode,
            },
            "mockmodule": "repository.lib.mock_device",
            "mockclass": "MockDevice",
        },
        "toptica_679": {
            "type": "local",
            "module": "toptica_wrapper.driver",
            "class": "TopticaDLCPro",
            "arguments": {
                "ip": "toptica-461-679",
                "laser": "laser2",
                "simulation": simulation_mode,
            },
            "mockmodule": "repository.lib.mock_device",
            "mockclass": "MockDevice",
        },
        "toptica_1379": {
            "type": "local",
            "module": "toptica_wrapper.driver",
            "class": "TopticaDLCPro",
            "arguments": {
                "ip": "toptica-1379-698",
                "laser": "laser1",
                "falc": 1,
                "simulation": simulation_mode,
            },
            "mockmodule": "repository.lib.mock_device",
            "mockclass": "MockDevice",
        },
        "toptica_698": {
            "type": "local",
            "module": "toptica_wrapper.driver",
            "class": "TopticaDLCPro",
            "arguments": {
                "ip": "toptica-1379-698",
                "laser": "laser2",
                "falc": 2,
                "simulation": simulation_mode,
            },
            "mockmodule": "repository.lib.mock_device",
            "mockclass": "MockDevice",
        },
        "toptica_707": {
            "type": "local",
            "module": "toptica_wrapper.driver",
            "class": "TopticaDLCPro",
            "arguments": {
                "ip": "toptica-707-689",
                "laser": "laser1",
                "simulation": simulation_mode,
            },
            "mockmodule": "repository.lib.mock_device",
            "mockclass": "MockDevice",
        },
        "toptica_689": {
            "type": "local",
            "module": "toptica_wrapper.driver",
            "class": "TopticaDLCPro",
            "arguments": {
                "ip": "toptica-707-689",
                "laser": "laser2",
                "falc": 1,
                "simulation": simulation_mode,
            },
            "mockmodule": "repository.lib.mock_device",
            "mockclass": "MockDevice",
        },
        "toptica_487": {
            "type": "local",
            "module": "toptica_wrapper.driver",
            "class": "TopticaDLCPro",
            "arguments": {
                "ip": "toptica-487-641",
                "laser": "laser1",
                "simulation": simulation_mode,
            },
            "mockmodule": "repository.lib.mock_device",
            "mockclass": "MockDevice",
        },
        "toptica_641": {
            "type": "local",
            "module": "toptica_wrapper.driver",
            "class": "TopticaDLCPro",
            "arguments": {
                "ip": "toptica-487-641",
                "laser": "laser2",
                "simulation": simulation_mode,
            },
            "mockmodule": "repository.lib.mock_device",
            "mockclass": "MockDevice",
        },
        "random_quotes": {
            "type": "controller",
            "host": "10.137.1.20",  # This is the raspberry pi running the TV by the door
            "port": 4321,
            "command": "aqctl_quotes --id 1234 --port {port} --bind {bind} -v",
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
