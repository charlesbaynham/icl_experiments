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
    # %% SUServos
    # Blue
    "suservo_aom_doublepass_461_injection": "suservo1_ch3",
    "suservo_aom_singlepass_461_spectroscopy": "suservo1_ch7",
    "suservo_aom_singlepass_461_pushbeam": "suservo1_ch2",
    "suservo_aom_singlepass_461_2dmot_a": "suservo1_ch0",
    "suservo_aom_singlepass_461_2dmot_b": "suservo1_ch1",
    "suservo_aom_singlepass_461_3DMOT_radial": "suservo1_ch4",
    "suservo_aom_singlepass_461_3DMOT_axialplus": "suservo1_ch5",
    "suservo_aom_singlepass_461_3DMOT_axialminus": "suservo1_ch6",
    "suservo_aom_singlepass_461_chamber2_imaging": "suservo0_ch0",
    # Red
    "urukul9910_aom_doublepass_689_red_injection": "urukul8_ch0",
    "suservo_aom_singlepass_689_redMOT_diag": "suservo2_ch4",
    "suservo_aom_singlepass_689_up": "suservo2_ch5",
    "suservo_aom_singlepass_689_redMOT_axialplus": "suservo2_ch6",
    "suservo_aom_singlepass_689_redMOT_axialminus": "suservo2_ch7",
    # Other
    "suservo_aom_singlepass_707": "suservo2_ch0",
    "suservo_aom_singlepass_679": "suservo2_ch1",
    "suservo_aom_singlepass_1379": "suservo2_ch2",
    # %% TTLs
    "TTL_shutter_461_pushbeam": "ttl16",
    "TTL_shutter_461_2dmot_is_it_a": "ttl17",
    "TTL_shutter_461_2dmot_is_it_b": "ttl18",
    "TTL_shutter_461_3dmot": "ttl19",
    "TTL_shutter_679_temporary_shutter": "ttl22",
    "TTL_shutter_707_temporary_shutter": "ttl23",
    "ttl_shutter_repump_707": "ttl24",
    "ttl_shutter_repump_679": "ttl25",
    "ttl_shutter_red_sigmaplus": "ttl26",
    "ttl_shutter_red_sigmaminus": "ttl27",
    "ttl_shutter_red_axial_mox": "ttl28",
    "ttl_shutter_red_up": "ttl29",
    "ttl_shutter_red_diagonal_mot": "ttl30",
    "ttl_shutter_red_axial_spin_pol": "ttl31",
    "zotino_plant_room": "zotino0",
    "ttl_transfer_cavity_trigger": "ttl1",
    "dds_transfer_cavity_aom": "urukul2_ch0",
    "eom_cavity_offset_689": "mirny0_ch0",
}
