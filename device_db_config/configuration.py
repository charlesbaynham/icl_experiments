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
    },
    "mot_photodiode_sampler_config": ("suservo0", 0),
    "zotino_plant_room_channels": {
        "ch1_coils_MOT": 0,
        "ch2_coils_x": 26,
        "ch2_coils_y": 25,
        "ch2_coils_z": 24,
    },
    "chamber_2_coil_x": VoltageControlledCurrentSupply("zotino_plant_room", 26, -2.0),
    "chamber_2_coil_y": VoltageControlledCurrentSupply("zotino_plant_room", 25, -2.0),
    "chamber_2_coil_z": VoltageControlledCurrentSupply("zotino_plant_room", 24, -1.0),
    "chamber_2_coil_mot": VoltageControlledCurrentSupply("zotino_plant_room", 0, 50.0),
}
