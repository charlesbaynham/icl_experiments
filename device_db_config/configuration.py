"""
Hardware configuration
======================

This module can hold free-form data of any type. It should be used to represent
hardware state in the lab . It should
NOT be used to represent information about running that hardware. For example:

In scope for this module:
#########################

* which cable is plugged in to which channel on the Sampler?
* which cable is plugged in to which channel on the Zotino?
* what gain is a particular photodiode set at?
* what gain is a current modulation input on a laser controller set to?
* which Sampler input channel is paired with which Urukul output channel?

Out of scope for this module (put this in :mod:`repository.lib.constants`):
#############################################################

* which attenuation do we usually run this coil at?
* what setpoint do we use for this SUServo?
* what temperature is our laser set to?

To retrieve information from this file in an experiment, use
:meth:`device_db_config.get_configuration_from_db` like so::

    from device_db_config import get_configuration_from_db

    data = get_configuration_from_db("my_data_item")

"""

from pydantic.dataclasses import dataclass


@dataclass
class VoltageControlledCurrentSupply:
    zotino: str
    "Name of zotino device in device_db"

    zotino_channel: int
    "Zotino channel controlling the supply"

    gain: float
    "Current gain in amps per volt"


config = {
    "IJD_monitors": {
        "blue_IJD1_controller": ("sampler2", 0),
        "blue_IJD2_controller": ("sampler2", 1),
        "blue_IJD3_controller": ("sampler2", 2),
        "red_IJD1_controller": ("sampler2", 3),
    },
    "IJD_info": {
        "blue_IJD1_controller": {
            "mod_gain": 0.75e-3,  # A/V
            "input_resistance": 50,  # Ohm
            "output_resistance": 50,  # Ohm
        },
        "blue_IJD2_controller": {
            "mod_gain": 0.75e-3,  # A/V
            "input_resistance": 50,  # Ohm
            "output_resistance": 50,  # Ohm
        },
        "blue_IJD3_controller": {
            "mod_gain": 0.75e-3,  # A/V
            "input_resistance": 50,  # Ohm
            "output_resistance": 50,  # Ohm
        },
        "red_IJD1_controller": {
            "mod_gain": 2.5e-3,  # A/V
            "input_resistance": 50,  # Ohm
            "output_resistance": 50,  # Ohm
        },
    },
    "chamber_2_coil_x": VoltageControlledCurrentSupply("zotino_plant_room", 26, -2.0),
    "chamber_2_coil_y": VoltageControlledCurrentSupply("zotino_plant_room", 25, -2.0),
    "chamber_2_coil_z": VoltageControlledCurrentSupply("zotino_plant_room", 24, -1.0),
    "chamber_2_coil_mot": VoltageControlledCurrentSupply(
        "zotino_plant_room", 0, 50.0 / 1.086
    ),
}
