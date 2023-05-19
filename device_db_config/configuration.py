"""
Hardware configuration
======================

This module can hold free-form data of any type. It should be used to represent
hardware state in the lab (e.g. "which cable is plugged in where" or "which
sampler input channel is paired with which urukul output channel"). It should
NOT be used to represent information like "which power we usually run this AOM
at" or "what current this coil typically needs" - that information belongs in
`constants.py`.

To retrieve information from this file in an experiment, use
:meth:`.get_configuration_from_db` like so::

    from device_db_config import get_configuration_from_db

    data = get_configuration_from_db("my_data_item")

"""


config = {
    "IJD_monitors": {
        "blue_IJD1_controller": ("sampler2", 0),
        "blue_IJD2_controller": ("sampler2", 1),
        "blue_IJD3_controller": ("sampler2", 2),
    },
    "mot_photodiode_sampler_config": ("suservo0", 0),
}
