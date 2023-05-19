"""
List of aliases for the hardware devices present in _device_db.py.

Entries in the form `<ARTIQ device name>: str` allow you to refer
to devices in EnvExperiments by a new alias instead
of their hardware address. These should be friendly names that
describe the purpose of a connection. This file will therefore serve
as a complete record of what cables were plugged in where at any point in time.

Entries of any other format are also allowed. These will be ignored by ARTIQ,
but your code can use them via `self.get_device_db()`. They should be used to store
any other information that is required to know the physical state of the lab,
e.g. "which channel on the sampler does what?". Note: these are not for storing
information like "optimal drive power for this AOM": that information belongs in
`constants.py`.
"""


aliases = {
    "suservo_aom_doublepass_461_injection": "suservo1_ch3",
    "suservo_aom_singlepass_461_spectroscopy": "suservo1_ch7",
    "suservo_aom_singlepass_461_pushbeam": "suservo1_ch2",
    "suservo_aom_singlepass_461_2dmot_a": "suservo1_ch0",
    "suservo_aom_singlepass_461_2dmot_b": "suservo1_ch1",
    "suservo_aom_singlepass_461_3DMOT_radial": "suservo1_ch4",
    "suservo_aom_singlepass_461_3DMOT_axialplus": "suservo1_ch5",
    "suservo_aom_singlepass_461_3DMOT_axialminus": "suservo1_ch6",
    "suservo_aom_singlepass_461_chamber2_imaging": "suservo0_ch0",
    "TTL_shutter_461_pushbeam": "ttl16",
    "TTL_shutter_461_2dmot_is_it_a": "ttl17",
    "TTL_shutter_461_2dmot_is_it_b": "ttl18",
    "TTL_shutter_461_3dmot": "ttl19",
    "TTL_shutter_679_temporary_shutter": "ttl22",
    "TTL_shutter_707_temporary_shutter": "ttl23",
    "zotino_plant_room": "zotino0",
}
