"""
This folder contains descriptions of lab devices, required to build a device_db
for the lab. The auto-generated ARTIQ "_device_db.py" is the description of the
ARTIQ core system, as built by the AION gateware pipeline / provided by M-Labs.
The "_non_core_devices.py" is a good place to store descriptions of peripheral
devices, connected by USB / ethernet / other interfaces to the PC running
artiq_master. "_aliases.py" is intended to hold human-friendly names of other
devices, so you can relabel devices / channels by purpose.

These three sources will be merged together when :meth:`.get_device_db` is called.
"""
from .devices import get_device_db


__all__ = [get_device_db]
