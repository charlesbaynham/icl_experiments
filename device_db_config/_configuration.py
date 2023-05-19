"""
Hardware configuration

This module can hold free-form data of any type. It should be used to represent
hardware state in the lab (e.g. "which cable is plugged in where" or "which
sampler input channel is paired with which urukul output channel"). It should
NOT be used to represent information like "which power we usually run this AOM
at" or "what current this coil typically needs" - that information belongs in
`constants.py`.

To retrieve information from this file in an experiment, use `

"""


config = {
    "IJD_monitors": {
        "type": "config",
        "data": {
            "blue_IJD1_controller": ("sampler2", 0),
            "blue_IJD2_controller": ("sampler2", 1),
            "blue_IJD3_controller": ("sampler2", 2),
        },
    },
    "mot_photodiode_sampler_config": {
        "type": "config",
        "data": ("suservo0", 0),
    },
}
