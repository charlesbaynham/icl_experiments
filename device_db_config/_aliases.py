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
    "urukul9910_aom_doublepass_461_master_to_ijd1": "urukul5_ch3",
    "urukul9910_aom_singlepass_461_ijd1_to_ijd23": "urukul5_ch2",
    "urukul9910_aom_doublepass_461_to_xfer_cavity": "urukul5_ch1",
    "suservo_aom_singlepass_461_imaging_delivery": "suservo1_ch3",
    "suservo_aom_singlepass_461_pushbeam": "suservo1_ch2",
    "suservo_aom_singlepass_689_molasses": "suservo1_ch0",
    "suservo_aom_singlepass_461_2dmot_b": "suservo1_ch1",
    "suservo_aom_singlepass_461_3DMOT_radial": "suservo1_ch4",
    "suservo_aom_singlepass_461_3DMOT_axialminus": "suservo1_ch5",
    "suservo_aom_singlepass_461_3DMOT_axialplus": "suservo1_ch6",
    "urukul9912_aom_singlepass_461_imaging_switch": "urukul2_ch3",
    "suservo_aom_singlepass_487_transparency": "suservo1_ch7",
    # Red
    "urukul9910_aom_doublepass_689_red_injection": "urukul8_ch0",
    "urukul9910_aom_doublepass_689_red_spinpol": "urukul8_ch1",
    "suservo_aom_singlepass_689_red_mot_diagonal": "suservo2_ch2",
    "suservo_aom_singlepass_689_up": "suservo2_ch5",
    "suservo_aom_singlepass_689_red_mot_sigmaplus": "suservo2_ch6",
    "suservo_aom_singlepass_689_red_mot_sigmaminus": "suservo2_ch7",
    "suservo_aom_singlepass_689_stark_shifter": "suservo2_ch3",
    "urukul9912_aom_singlepass_689_stark_shifter_switch": "urukul2_ch0",
    # 1064
    "suservo_aom_1064_delivery": "suservo0_ch3",
    # Other 1064 channels
    "suservo_aom_1064_painted_delivery": "suservo0_ch4",
    "urukul9910_aom_1064_painting": "urukul5_ch0",
    "suservo_aom4_1064": "suservo0_ch5",
    # 813 channels
    "suservo_aom_down_813": "suservo0_ch7",
    "suservo_aom_up_813": "suservo0_ch6",
    # Other
    "suservo_aom_singlepass_707": "suservo2_ch0",
    "suservo_aom_singlepass_679": "suservo2_ch1",
    "suservo_aom_singlepass_1379_cavity_input": "suservo2_ch4",
    "urukul9910_aom_698_up_switch": "urukul2_ch2",
    "urukul9910_aom_698_down_switch": "urukul2_ch1",
    "urukul9910_OPLL_698_clock": "urukul8_ch2",
    "suservo_aom_698_clock_delivery": "suservo0_ch0",
    "suservo_aom_698_squeezing_cavity_transmission": "suservo0_ch2",
    "urukul_squeezing_probe": "urukul8_ch3",
    # %% TTLs
    # ttl0-3 bank set to In/Out
    "ttl_50hz_trigger": "ttl1",
    # other TTLs are all set to Output:
    "ttl_camera_trigger_andor": "ttl4",
    "ttl_shutter_andor": "ttl5",
    "ttl_camera_trigger_horizontal": "ttl6",
    "ttl_camera_trigger_vertical": "ttl7",
    "TTL_shutter_461_pushbeam": "ttl8",
    "TTL_shutter_461_2dmot_is_it_a": "ttl9",
    "TTL_shutter_461_2dmot_is_it_b": "ttl10",
    "TTL_shutter_461_3dmot": "ttl11",
    "ttl_clock_glitch_counter": "ttl12",
    "ttl_698_opll_enable": "ttl14",
    "ttl_shutter_repump_707": "ttl16",
    "ttl_shutter_repump_679": "ttl17",
    "ttl_shutter_red_sigmaplus": "ttl18",
    "ttl_shutter_red_sigmaminus": "ttl19",
    "ttl_shutter_red_axial_mot": "ttl20",
    "ttl_shutter_red_up": "ttl21",
    "ttl_shutter_red_mot_diagonal": "ttl22",
    "ttl_shutter_red_axial_spin_pol": "ttl23",
    "ttl_shutter_red_wavemeter_689_master": "ttl24",
    "ttl_shutter_red_wavemeter_689_from_1379": "ttl25",
    # %% Mirny
    "mirny_eom_waveguide_1379": "mirny0_ch0",
    "mirny_eom_707_sideband_A": "mirny0_ch1",
    "mirny_eom_707_sideband_B": "mirny0_ch2",
    "mirny_eom_689_sideband": "mirny0_ch3",
    # %% Other
    "zotino_plant_room": "zotino0",
}
