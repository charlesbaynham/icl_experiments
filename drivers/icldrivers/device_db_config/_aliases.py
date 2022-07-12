# List of aliases for the hardware devices present in _device_db.py.
# These should be friendly names that describe the purpose of a connection.
# These are just examples, add your own!
aliases = {
    "dds_transfer_cavity_aom": "urukul0_ch2",
    "ttl_transfer_cavity_trigger": "ttl13",
    # It's also possible to store generic information here about the hardware
    # configuration of your experiment. For example, let's imagine that I need
    # to record the polarity of a coil driver's connection to a coil, I could use:
    "coil_polarity": "positive",
    # and could retrieve that information with
    #     self.get_device_db()["coil_polarity"]
}
